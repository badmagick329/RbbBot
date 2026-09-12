from rbb_bot.infrastructure.privacy.user_data import UserDataService


class StoredTagPreferences:
    def is_opted_out(self, user_id: int) -> bool:
        return UserDataService.is_tag_opted_out(user_id)
