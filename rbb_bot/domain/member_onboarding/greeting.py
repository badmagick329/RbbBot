from dataclasses import dataclass


@dataclass(frozen=True)
class GreetingTemplate:
    title: str
    description: str
    show_member_count: bool
