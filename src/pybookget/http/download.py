"""Download manager with concurrent file-level downloads (async-only).

File-level resumability: Files are skipped if they already exist.
No below-file-level parallelization or chunking.

Tasks are streamed: ``run()`` takes any iterable or async iterable of
DownloadTasks and keeps only a small bounded queue of them in memory, so it
handles millions of files at constant memory. ``execute()`` runs the tasks
queued with ``add_task()``/``add_tasks()`` the same way.
"""

import asyncio
import logging
from collections.abc import AsyncIterable, Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

import httpx
from tqdm import tqdm

from pybookget.config import Config
from pybookget.http.client import create_client, download_file

logger = logging.getLogger(__name__)


@dataclass
class DownloadTask:
    """A single download task with URL and destination."""

    url: str
    save_path: Path
    book_id: str = ""
    title: str = ""
    volume_id: str = ""
    headers: dict | None = None
    fallback_url: str | None = None  # Try this URL if primary fails with 404
    error: str | None = None  # Set by the manager when the download failed

    def __post_init__(self):
        """Ensure save_path is a Path object."""
        if isinstance(self.save_path, str):
            self.save_path = Path(self.save_path)


@dataclass
class DownloadStats:
    """Outcome counts of a download run."""

    successful: int = 0  # downloaded now, plus skipped
    failed: int = 0
    skipped: int = 0  # already existed (counted in successful too)


Callback = Callable[[DownloadTask, bool], None]


class DownloadManager:
    """Manages concurrent file downloads with progress tracking (async-only).

    Features:
    - File-level resumability (skip existing files)
    - Concurrent downloads (``max_workers`` files in parallel)
    - Streaming: bounded memory for any number of tasks
    - Results reported per task (callback and ``task.error``)
    - Progress tracking with tqdm
    """

    def __init__(
        self,
        config: Config,
        max_workers: int | None = None,
        show_progress: bool = True,
    ):
        """Initialize download manager.

        Args:
            config: Configuration object
            max_workers: Maximum number of concurrent downloads (defaults to config)
            show_progress: Whether to show progress bar
        """
        self.config = config
        self.max_workers = max_workers or config.threads_per_task
        self.show_progress = show_progress and config.show_progress
        self.tasks: list[DownloadTask] = []

    def add_task(self, task: DownloadTask):
        """Add a download task to the queue.

        Args:
            task: DownloadTask to add
        """
        self.tasks.append(task)

    def add_tasks(self, tasks: list[DownloadTask]):
        """Add multiple download tasks to the queue.

        Args:
            tasks: List of DownloadTask objects to add
        """
        self.tasks.extend(tasks)

    async def execute(self, callback: Callback | None = None) -> int:
        """Execute all queued download tasks concurrently.

        Args:
            callback: Optional callback function called after each task completes
                     with signature: callback(task, success)

        Returns:
            Number of successfully downloaded files (including skipped existing files)
        """
        if not self.tasks:
            logger.warning("No tasks to execute")
            return 0

        tasks, self.tasks = self.tasks, []
        stats = await self.run(tasks, callback=callback)
        return stats.successful

    async def run(
        self,
        tasks: Iterable[DownloadTask] | AsyncIterable[DownloadTask],
        callback: Callback | None = None,
        total: int | None = None,
    ) -> DownloadStats:
        """Download a stream of tasks with ``max_workers`` concurrent downloads.

        Tasks are pulled from ``tasks`` only as workers become free (at most
        ``2 * max_workers`` are waiting at any time), so ``tasks`` can be a
        generator over millions of files.

        Args:
            tasks: Iterable or async iterable of DownloadTasks
            callback: Optional ``callback(task, success)`` called once per task,
                with the task the result belongs to. A failing callback is
                logged and does not stop the run.
            total: Number of tasks for the progress bar (defaults to len(tasks)
                when available)

        Returns:
            DownloadStats with successful, failed and skipped counts
        """
        stats = DownloadStats()
        workers = max(1, self.max_workers)
        queue: asyncio.Queue = asyncio.Queue(maxsize=2 * workers)
        done = object()  # sentinel telling a worker to stop

        if total is None and hasattr(tasks, "__len__"):
            total = len(tasks)  # type: ignore[arg-type]
        pbar = tqdm(total=total, desc="Downloading", unit="file") if self.show_progress else None

        client = create_client(self.config)

        async def produce():
            if isinstance(tasks, AsyncIterable):
                async for task in tasks:
                    await queue.put(task)
            else:
                for task in tasks:
                    await queue.put(task)

        async def work():
            while True:
                task = await queue.get()
                try:
                    if task is done:
                        return
                    try:
                        await self._process(client, task, stats, callback)
                    except Exception as e:  # never let one task stop a worker
                        task.error = f"{type(e).__name__}: {e}"
                        stats.failed += 1
                        logger.error(f"Unexpected error for {task.url}: {e}")
                    if pbar:
                        pbar.update(1)
                        pbar.set_postfix({"success": stats.successful, "failed": stats.failed})
                finally:
                    queue.task_done()

        worker_tasks = [asyncio.create_task(work()) for _ in range(workers)]
        try:
            await produce()
            for _ in worker_tasks:
                await queue.put(done)
            await asyncio.gather(*worker_tasks)
        finally:
            for worker in worker_tasks:
                worker.cancel()
            await asyncio.gather(*worker_tasks, return_exceptions=True)
            await client.aclose()
            if pbar:
                pbar.close()

        logger.info(
            f"Download complete: {stats.successful} successful "
            f"({stats.skipped} already present), {stats.failed} failed"
        )
        return stats

    async def _process(
        self,
        client: httpx.AsyncClient,
        task: DownloadTask,
        stats: DownloadStats,
        callback: Callback | None,
    ) -> None:
        """Download one task, update stats and report it to the callback."""
        if task.save_path.exists():
            stats.skipped += 1
            success = True
        else:
            success = await self._download_single(client, task)
        if success:
            stats.successful += 1
        else:
            stats.failed += 1

        if callback:
            try:
                callback(task, success)
            except Exception as e:
                logger.error(f"Callback failed for {task.url}: {e}")

    async def _download_single(self, client: httpx.AsyncClient, task: DownloadTask) -> bool:
        """Download a single file with tenacity retry logic and fallback support.

        Args:
            client: httpx.AsyncClient instance
            task: DownloadTask to execute

        Returns:
            True if successful, False otherwise (``task.error`` says why)
        """
        # Try primary URL first
        try:
            await download_file(
                client=client,
                url=task.url,
                dest_path=task.save_path,
                config=self.config,
                headers=task.headers,
            )

            # Rate limiting if configured
            if self.config.sleep_interval > 0:
                await asyncio.sleep(self.config.sleep_interval)

            logger.debug(f"Downloaded: {task.url} -> {task.save_path}")
            return True

        except httpx.HTTPStatusError as e:
            # If primary URL fails with 404 and we have a fallback, try it
            if e.response.status_code == 404 and task.fallback_url:
                logger.warning(f"Primary URL returned 404, trying fallback: {task.fallback_url}")
                try:
                    await download_file(
                        client=client,
                        url=task.fallback_url,
                        dest_path=task.save_path,
                        config=self.config,
                        headers=task.headers,
                    )

                    if self.config.sleep_interval > 0:
                        await asyncio.sleep(self.config.sleep_interval)

                    logger.info(f"Fallback succeeded: {task.fallback_url} -> {task.save_path}")
                    return True

                except Exception as fallback_error:
                    task.error = f"{type(fallback_error).__name__}: {fallback_error}"
                    logger.error(f"Fallback also failed for {task.fallback_url}: {fallback_error}")
                    return False
            else:
                task.error = f"HTTP {e.response.status_code}"
                logger.error(f"Failed to download {task.url}: {e}")
                return False

        except Exception as e:
            task.error = f"{type(e).__name__}: {e}"
            logger.error(f"Failed to download {task.url} after retries: {e}")
            return False

    def clear(self):
        """Clear all queued tasks."""
        self.tasks = []

    def __len__(self):
        """Return number of queued tasks."""
        return len(self.tasks)
