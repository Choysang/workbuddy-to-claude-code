import argparse
import sys

from . import storage
from .models import Task


def format_task(task):
    mark = "x" if task.done else " "
    return f"[{mark}] {task.id}: {task.title}"


def build_parser():
    parser = argparse.ArgumentParser(prog="todo")
    sub = parser.add_subparsers(dest="command", required=True)
    add = sub.add_parser("add")
    add.add_argument("title")
    sub.add_parser("list")
    done = sub.add_parser("done")
    done.add_argument("id", type=int)
    return parser


def main(argv, store_path, out=None):
    out = out or sys.stdout
    args = build_parser().parse_args(argv)
    tasks = storage.load(store_path)
    if args.command == "add":
        task = Task(id=storage.next_id(tasks), title=args.title)
        tasks.append(task)
        storage.save(store_path, tasks)
        print(f"added {task.id}", file=out)
    elif args.command == "list":
        for task in tasks:
            print(format_task(task), file=out)
    elif args.command == "done":
        for task in tasks:
            if task.id == args.id:
                task.done = True
                storage.save(store_path, tasks)
                print(f"done {task.id}", file=out)
                return 0
        print(f"no task {args.id}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:], "todo.json"))
