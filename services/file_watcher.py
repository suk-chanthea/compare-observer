"""File watching services"""
import os
import hashlib
import threading
from PyQt6.QtCore import QThread, pyqtSignal, QCoreApplication, QObject
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from core.events import FileUpdateEvent, FileCreateEvent, FileDeleteEvent
from config import DEBUG


class WatcherThread(QThread):
    started_watching = pyqtSignal()
    stopped_watching = pyqtSignal()
    preload_complete = pyqtSignal()  # Signal to notify when preload is complete

    def __init__(self, table_index, table, path, excluded_folders, excluded_files, dialog):
        super().__init__()
        self.table = table
        self.path = path
        self.excluded_folders = excluded_folders
        self.excluded_files = excluded_files
        self.dialog = dialog
        self.table_index = table_index

        self.observer = Observer()
        self._running = False

    def run(self):
        self._running = True
        self.event_handler = FileEventHandler(self.table, self.path, self.excluded_folders, self.excluded_files, self.dialog)
        self.observer.schedule(self.event_handler, self.path, recursive=True)
        self.observer.start()

        # Preload file hashes first
        self.event_handler.preload_file_hashes(self.table_index)

        # Emit signal after preloading is complete
        self.preload_complete.emit()  # Notify that file preloading is finished'
        # Emit started_watching signal after preload is done
        self.started_watching.emit()

        try:
            while self._running:
                self.msleep(300)  # Prevent blocking GUI
        except Exception as e:
            print(f"Exception in WatcherThread: {e}")
        finally:
            self.stop_observer()  # Ensure observer is properly stopped
            self.stopped_watching.emit()

    def stop(self):
        self._running = False
        self.event_handler.stopp_reload_file_hashes()
        self.stop_observer()
        self.quit()  # Ensures thread exits properly
        self.wait()  # Waits for thread to finish

    def stop_observer(self):
        if self.observer.is_alive():  # Check if observer is still running
            self.observer.stop()
            self.observer.join()
            print("Observer stopped.")


class FileEventHandler(FileSystemEventHandler, QObject):
    def __init__(self, table, watch_path, excluded_folders, excluded_files, dialog):
        super().__init__()
        self.table = table
        self.watch_path = watch_path
        self.excluded_folders = excluded_folders
        self.excluded_files = excluded_files
        self.file_hashes = {}  # Dictionary to store last known file hashes
        self.load_file_hash = True
        self.preload_complete = False  # Flag to ignore events until baseline is captured
        self.dialog = dialog

    def stopp_reload_file_hashes(self):
        self.load_file_hash = False
        
    def calculate_file_hash(self, file_path, keep_hash=True):
        """Calculate and cache the file hash based solely on its content."""
        forward_slash_path = file_path.replace("\\", "/")
        try:
            hasher = hashlib.md5()
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):  # Read in chunks for efficiency
                    hasher.update(chunk)

            file_hash = hasher.hexdigest()
            if keep_hash:
                self.file_hashes[forward_slash_path] = file_hash
            return file_hash
        except Exception as e:
            print(f"Error reading file {file_path}: {e}")
            return None
        
    def preload_file_hashes(self, table_index):
        print(f"Preloading file hashes for table {table_index}")
        threads = []
        lock = threading.Lock()  # Lock to ensure thread-safe dictionary updates

        def process_file(file_path):
            """Hash a file and update the dictionary safely. Also capture file content as baseline."""
            if not self.load_file_hash:
                return

            file_hash = self.calculate_file_hash(file_path)
            if file_hash:
                with lock:  # Ensure thread-safe update
                    self.file_hashes[file_path] = file_hash
                    print(f"{file_path}=>{file_hash}")
                    
                    # Capture file content as "old" baseline when scanning starts
                    try:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            content = f.read()
                            self.table.file_contents[file_path] = content
                            from config import DEBUG
                            if DEBUG:
                                print(f"Captured baseline content for: {file_path}")
                    except Exception as e:
                        print(f"Error capturing baseline content for {file_path}: {e}")
                        self.table.file_contents[file_path] = None
                        
                self.dialog.add_log_signal.emit(file_path)

        for root, dirs, files in os.walk(self.watch_path):
            if not self.load_file_hash:
                print("Stopped preloading file hashes")
                return

            root = root.replace("\\", "/")  # Convert paths for cross-platform compatibility
            dirs[:] = [d for d in dirs if not self._is_excluded(os.path.join(root, d))]  # Skip excluded dirs

            for file in files:
                if not self.load_file_hash:
                    print("Stopped preloading file hashes")
                    return

                file_path = os.path.join(root, file).replace("\\", "/")
                if not self._is_excluded(file_path):
                    thread = threading.Thread(target=process_file, args=(file_path,))
                    thread.start()
                    threads.append(thread)

        # Wait for all threads to finish
        for thread in threads:
            thread.join()
        
        # Mark preload as complete - now we can start processing file change events
        self.preload_complete = True
        print(f"Preload complete for table {table_index}, baseline captured for all files")
        
    def on_modified(self, event):
        """Handle file modifications efficiently."""
        # Ignore all events until preload is complete (baseline captured)
        if not self.preload_complete:
            return
            
        if event.is_directory:
            return  # Ignore directory-level modifications
        
        file_path = os.path.normpath(event.src_path)
        if self._is_excluded(file_path) or event.is_directory:
            return
        
        # Calculate the new hash for the file
        new_hash = self.calculate_file_hash(file_path, False)
        forward_slash_path = file_path.replace("\\", "/")
        if DEBUG:
            print(f"new_hash={forward_slash_path} {new_hash}")
        if new_hash:
            if forward_slash_path not in self.file_hashes:
                if DEBUG:
                    print(f"add hash")
                self.file_hashes[forward_slash_path] = new_hash
            else:
                if DEBUG:
                    print(f"check hash {self.file_hashes[forward_slash_path]}, {new_hash}")

                if self.file_hashes[forward_slash_path] != new_hash:
                    if DEBUG:
                        print(f"upt hash")

                    self.file_hashes[forward_slash_path] = new_hash
                    QCoreApplication.postEvent(self.table, FileUpdateEvent(self.table, file_path))

    def on_created(self, event):
        if self._is_excluded(event.src_path):
            print(f"Skipping on_created {event.src_path}")
            return

        file_path = event.src_path
        file_hash = self.calculate_file_hash(file_path)
        
        if file_hash:
            forward_slash_path = file_path.replace("\\", "/")
            self.file_hashes[forward_slash_path] = file_hash         
            # Create and post event
            event_obj = FileCreateEvent(self.table, file_path)
            QCoreApplication.postEvent(self.table, event_obj)

    def on_deleted(self, event):
        if self._is_excluded(event.src_path):
            print(f"Skipping on_deleted {event.src_path}")
            return
        
        if not event.is_directory:
            file_path = event.src_path
            forward_slash_path = file_path.replace("\\", "/")
            if forward_slash_path in self.file_hashes:
                del self.file_hashes[forward_slash_path]  # Remove the file from the hash dictionary
                print(f"File deleted: {forward_slash_path}")
                # Handle the deletion event as needed
                QCoreApplication.postEvent(self.table, FileDeleteEvent(self.table, file_path))

    def _is_excluded(self, path):
        excluded_paths = [os.path.join(self.watch_path, folder) for folder in self.excluded_folders]
        # Normalize the path
        abs_path = os.path.abspath(path)
        basename = os.path.basename(path)
        # Check if path is inside any excluded folder
        if any(abs_path.startswith(os.path.abspath(folder)) for folder in excluded_paths):
            return True
        
        if basename in self.excluded_files:
            return True

        return False

