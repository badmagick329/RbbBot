import discord
from discord.ext import commands


def cmd_to_str(group=False, indent=False):
    newline = "\n" if group else " "

    def actual(cmd):
        help_ = cmd.brief or cmd.help
        indent_ = "∙ " if indent else ""
        return f'{indent_}**{cmd.name}**{newline}{help_ or "No description"}\n'

    return actual


class EmbedHelpCommand(commands.DefaultHelpCommand):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def embed(self, name=None):
        bot = self.context.bot
        heading = f" - {name}" if name else ""
        return discord.Embed(description=self.get_ending_note()).set_author(
            name=f"{bot.user.name} help{heading}", icon_url=bot.user.avatar.url
        )

    @staticmethod
    def parse_help_text(text):
        parsed_lines = list()
        parsing_args = False
        for line in text.splitlines():
            if "Parameters" in line:
                parsed_lines.append("**Parameters**")
                continue
            if "----------" in line:
                parsing_args = True
                continue
            if parsing_args:
                if line.startswith("    ") and line.strip():
                    parsed_lines.append(line.strip())
                else:
                    parsed_lines.append(f"**{line.split(':')[0].strip()}**")
            else:
                parsed_lines.append(line)
        return "\n".join(parsed_lines)

    def format_help(self, text, name=None):
        text = text.format(prefix=self.context.clean_prefix, commend_name=name)
        return self.parse_help_text(text)

    async def send_cog_help(self, cog):
        name = type(cog).__name__
        await self.send_group_help(cog.bot.get_command(name.lower()))

    async def send_command_help(self, command):
        embed = self.embed(name=command.qualified_name)
        embed.add_field(
            name="Usage", value=self.get_command_signature(command), inline=False
        )
        if help_ := (command.help or command.brief):
            embed.add_field(
                name="Description",
                value=self.format_help(help_, name=command.qualified_name),
                inline=False,
            )

        await self.get_destination().send(embed=embed)

    async def send_group_help(self, group):
        embed = self.embed(name=group.qualified_name)
        embed.add_field(
            name="Usage", value=self.get_command_signature(group), inline=False
        )
        if help_ := (group.help or group.brief):

            embed.add_field(
                name="Description",
                value=self.format_help(help_, name=group.qualified_name),
                inline=False,
            )

        filtered = await self.filter_commands(group.commands, sort=self.sort_commands)

        groups = [group for group in filtered if isinstance(group, commands.Group)]
        cmds = [cmd for cmd in filtered if not isinstance(cmd, commands.Group)]

        if len(groups) > 0:
            embed.add_field(
                name="Categories",
                value="".join(map(cmd_to_str(group=True, indent=True), groups)),
                inline=False,
            )

        embed.add_field(
            name="Subcommands",
            value="".join(map(cmd_to_str(indent=True), cmds)),
            inline=False,
        )

        await self.get_destination().send(embed=embed)

    async def send_bot_help(self, mapping):
        ctx = self.context
        bot = ctx.bot

        filtered = await self.filter_commands(bot.commands, sort=self.sort_commands)

        groups = [group for group in filtered if isinstance(group, commands.Group)]
        top_level_commands = [
            cmd for cmd in filtered if not isinstance(cmd, commands.Group)
        ]

        embed = (
            self.embed()
            .add_field(
                name="Categories",
                value=" ".join(map(cmd_to_str(group=True), groups)),
                inline=False,
            )
            .add_field(
                name="Various",
                value=" ".join(map(cmd_to_str(), top_level_commands)),
                inline=False,
            )
        )

        await self.get_destination().send(embed=embed)
