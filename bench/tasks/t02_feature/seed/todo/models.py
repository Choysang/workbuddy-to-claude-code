from dataclasses import dataclass


@dataclass
class Task:
    id: int
    title: str
    done: bool = False

    def to_dict(self):
        return {"id": self.id, "title": self.title, "done": self.done}

    @classmethod
    def from_dict(cls, data):
        return cls(id=data["id"], title=data["title"], done=data.get("done", False))
