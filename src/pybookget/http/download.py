"""Download manager with concurrent file-level downloads (async-only).

File-level resumability: Files are skipped if they already exist.
No below-file-level parallelization or chunking.
"""

import asyncio
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List, Optional

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
    headers: Optional[dict] = None
    fallback_url: Optional[str] = None  # Try this URL if primary fails with 404

    def __post_init__(self):
        """Ensure save_path is a Path object."""
        if isinstance(self.save_path, str):
            self.save_path = Path(self.save_path)


class DownloadManager:
    """Manages concurrent file downloads with progress tracking (async-only).

    Features:
    - File-level resumability (skip existing files)
    - Concurrent downloads (multiple files in parallel)
    - No below-file-level parallelization
    - Progress tracking with tqdm
    - Async with asyncio.Semaphore for concurrency control
    """

    def __init__(
        self,
        config: Config,
        max_workers: Optional[int] = None,
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
        self.tasks: List[DownloadTask] = []

    def add_task(self, task: DownloadTask):
        """Add a download task to the queue.

        Args:
            task: DownloadTask to add
        """
        self.tasks.append(task)

    def add_tasks(self, tasks: List[DownloadTask]):
        """Add multiple download tasks to the queue.

        Args:
            tasks: List of DownloadTask objects to add
        """
        self.tasks.extend(tasks)

    async def execute(
        self,
        callback: Optional[Callable[[DownloadTask, bool], None]] = None
    ) -> int:
        """Execute all queued download tasks concurrently.

        Uses asyncio for concurrent downloads with Semaphore for concurrency control.

        Args:
            callback: Optional callback function called after each task completes
                     with signature: callback(task, success)

        Returns:
            Number of successfully downloaded files
        """
        if not self.tasks:
            logger.warning("No tasks to execute")
            return 0

        successful = 0
        failed = 0

        # Create async httpx client
        client = create_client(self.config)

        # Create progress bar if enabled
        pbar = None
        if self.show_progress:
            pbar = tqdm(total=len(self.tasks), desc="Downloading", unit="file")

        try:
            # Use asyncio.Semaphore to limit concurrent downloads
            semaphore = asyncio.Semaphore(self.max_workers)

            async def download_with_semaphore(task: DownloadTask):
                async with semaphore:
                    return await self._download_single(client, task)

            # Create all tasks
            download_tasks = [download_with_semaphore(task) for task in self.tasks]

            # Execute concurrently and process results
            for task, coro in zip(self.tasks, asyncio.as_completed(download_tasks)):
                try:
                    success = await coro
                    if success:
                        successful += 1
                    else:
                        failed += 1

                    # Call callback if provided
                    if callback:
                        callback(task, success)

                except Exception as e:
                    logger.error(f"Task failed with exception: {e}")
                    failed += 1

                # Update progress bar
                if pbar:
                    pbar.update(1)
                    pbar.set_postfix({"success": successful, "failed": failed})

        finally:
            await client.aclose()
            if pbar:
                pbar.close()

        # Clear tasks after execution
        self.tasks = []

        logger.info(f"Download complete: {successful} successful, {failed} failed")
        return successful

    async def _download_single(self, client: httpx.AsyncClient, task: DownloadTask) -> bool:
        """Download a single file with tenacity retry logic and fallback support.

        Args:
            client: httpx.AsyncClient instance
            task: DownloadTask to execute

        Returns:
            True if successful, False otherwise
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
                    logger.error(f"Fallback also failed for {task.fallback_url}: {fallback_error}")
                    return False
            else:
                logger.error(f"Failed to download {task.url}: {e}")
                return False

        except Exception as e:
            logger.error(f"Failed to download {task.url} after retries: {e}")
            return False

    def clear(self):
        """Clear all queued tasks."""
        self.tasks = []

    def __len__(self):
        """Return number of queued tasks."""
        return len(self.tasks)
