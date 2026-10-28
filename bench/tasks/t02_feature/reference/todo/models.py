from dataclasses import dataclass

PRIORITIES = ("high", "normal", "low")


@dataclass
class Task:
    id: int
    title: str
    done: bool = False
    priority: str = "normal"

    def to_dict(self):
        return {"id": self.id, "title": self.title, "done": self.done, "priority": self.priority}

    @classmethod
    def from_dict(cls, data):
        return cls(id=data["id"], title=data["title"], done=data.get("done", False),
                   priority=data.get("priority", "normal"))
