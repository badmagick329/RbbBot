from tortoise import fields
from tortoise.models import Model

from rbb_bot.models.encrypted import EncryptedModelMixin, EncryptedValue
from rbb_bot.settings.ids import CONF_CHANNEL_ID, CONF_GUILD_ID
from rbb_bot.utils.mixins import ClientMixin


class SourceEntry(EncryptedModelMixin, Model, ClientMixin):
    id = fields.IntField(pk=True)
    emoji_string_ciphertext = fields.TextField(null=True)
    emoji_lookup = fields.CharField(max_length=64, null=True, index=True)
    emoji_string = EncryptedValue(
        "emoji_string_ciphertext",
        lookup_field="emoji_lookup",
        normalize_lookup=str,
    )
    emoji_url_ciphertext = fields.TextField(null=True)
    emoji_url = EncryptedValue("emoji_url_ciphertext")
    source_url_ciphertext = fields.TextField(null=True)
    source_url = EncryptedValue("source_url_ciphertext")
    event_ciphertext = fields.TextField(null=True)
    event = EncryptedValue("event_ciphertext")
    source_date = fields.DateField(null=True)
    guild_id = fields.BigIntField(null=True)
    channel_id = fields.BigIntField()
    message_id = fields.BigIntField()
    jump_url_ciphertext = fields.TextField(null=True)
    jump_url = EncryptedValue("jump_url_ciphertext")
    user = fields.ForeignKeyField("models.DiscordUser", related_name="sources")
    conf_message_id = fields.BigIntField()
    conf_jump_url_ciphertext = fields.TextField(null=True)
    conf_jump_url = EncryptedValue("conf_jump_url_ciphertext")

    conf_channel_id = CONF_CHANNEL_ID
    conf_guild_id = CONF_GUILD_ID
    MAX_CHAR_FIELD = 255

    def __repr__(self):
        return (
            f"Source<(id={self.id}, emoji_string={self.emoji_string}, "
            f"emoji_url={self.emoji_url}, "
            f"source_url={self.source_url}, event={self.event}, "
            f"source_date={self.source_date}, guild_id={self.guild_id}, "
            f"channel_id={self.channel_id}, message_id={self.message_id}, "
            f"jump_url={self.jump_url}, user={self.user}, "
            f"conf_message_id={self.conf_message_id}, "
            f"conf_jump_url={self.conf_jump_url})>"
        )

    def __str__(self):
        return self.__repr__()
