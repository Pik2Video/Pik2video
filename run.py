# run.py
import os
import sys
import time
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class ReloadHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if any(event.src_path.endswith(ext) for ext in ('.py', '.pyc')):
            print("Изменения внесены... приложение перезапущено...")
            os.execl(sys.executable, sys.executable, *sys.argv)

if __name__ == "__main__":
    observer = Observer()
    observer.schedule(ReloadHandler(), path='./src/', recursive=True)
    observer.start()

    try:
        from src.main import main
        main()
    except KeyboardInterrupt:
        observer.stop()
        observer.join()