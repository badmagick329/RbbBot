from rbb_bot.services.user_data_service import UserDataService


class StoredTagPreferences:
    def is_opted_out(self, user_id: int) -> bool:
        return UserDataService.is_tag_opted_out(user_id)
