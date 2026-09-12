from discord import Embed
from rbb_bot.utils.views import ListView
from rbb_bot.utils.helpers import truncate


class TagsList(ListView):
    def create_embed(self, tags_and_responses: list[tuple[str, str]]) -> Embed:
        header = (
            f"{len(self.list_items)} {'Tags' if len(self.list_items) > 1 else 'Tag'}"
        )
        embed = Embed(
            title=f"Page {self.current_page + 1} of {len(self.view_chunks)}\n{header}"
        )

        for tnr in tags_and_responses:
            tag, response = tnr
            embed.add_field(name=tag, value=response, inline=False)

        return embed


class ResponsesList(ListView):
    def create_embed(self, ids_and_responses: list[tuple[str, str]]) -> Embed:
        header = f"{len(self.list_items)} {'Responses' if len(self.list_items) > 1 else 'Response'} found"
        embed = Embed(
            title=f"Page {self.current_page + 1} of {len(self.view_chunks)}\n{header}"
        )

        for id_and_response in ids_and_responses:
            id, response = id_and_response
            embed.add_field(name=id, value=response, inline=False)
        return embed


def tag_list_items(tags):
    result = []
    for tag in tags:
        response = (
            truncate(tag.responses[0].content, 160) if tag.responses else "No responses"
        )
        if len(tag.responses) > 1:
            response += f" and {len(tag.responses) - 1} more"
        result.append(
            (f"[{tag.id}] {tag.trigger}\nUsed {tag.use_count} times", response)
        )
    return result


def response_list_items(responses):
    return [
        (f"[{response.id}]", truncate(response.content, 160)) for response in responses
    ]
