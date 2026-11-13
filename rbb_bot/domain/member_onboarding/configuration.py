from rbb_bot.domain.member_onboarding.greeting import GreetingTemplate

DEFAULT_GREETING = GreetingTemplate("Welcome!", "Welcome to the server!", True)
MAX_TITLE = 155
MAX_DESCRIPTION = 3996
MAX_MESSAGE = 1900
MAX_AUTO_ROLES = 5


class OnboardingInputError(ValueError):
    pass


class MissingManageRoles(OnboardingInputError):
    def __init__(self):
        super().__init__("I need the Manage Roles permission to apply auto roles")


class UnassignableAutoRoles(OnboardingInputError):
    """Carries the skipped role IDs so the guild can be told exactly which roles to fix."""

    def __init__(self, role_ids: tuple[int, ...]):
        super().__init__(f"Unassignable auto roles: {role_ids}")
        self.role_ids = role_ids


def greeting_template(
    current: GreetingTemplate,
    title: str | None,
    description: str | None,
    show_count: bool,
) -> GreetingTemplate:
    title = current.title if title is None else title
    description = current.description if description is None else description
    if len(title) > MAX_TITLE:
        raise OnboardingInputError(f"Title must be at most {MAX_TITLE} characters")
    if len(description) > MAX_DESCRIPTION:
        raise OnboardingInputError(
            f"Message must be at most {MAX_DESCRIPTION} characters"
        )
    return GreetingTemplate(title, description, show_count)


def welcome_message(value: str) -> str:
    value = value.strip()
    if not value:
        raise OnboardingInputError("Message cannot be empty")
    if len(value) > MAX_MESSAGE:
        raise OnboardingInputError(f"Message must be at most {MAX_MESSAGE} characters")
    return value


def check_role_capacity(count: int) -> None:
    if count >= MAX_AUTO_ROLES:
        raise OnboardingInputError(
            f"You can only have a maximum of {MAX_AUTO_ROLES} auto roles per server"
        )
