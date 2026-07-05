from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from app.core.embeds import DefaultEmbed, ErrorEmbed
from app.db.models import DiaryEntry, Persona
from app.types import Interaction  # noqa: TC001
from app.ui import ActionRow, Button, Container, LayoutView, Select, TextDisplay

if TYPE_CHECKING:
    from app.core.bot import MyBot

# LayoutView caps total text at 4000 characters; leave headroom for the heading lines
DIARY_CONTENT_LIMIT = 3500
CHOICE_LIMIT = 25  # Discord autocomplete choice count limit


class DiaryView(LayoutView):
    def __init__(self, personas: list[Persona]) -> None:
        super().__init__()
        self.personas = personas
        self.selected: Persona | None = None
        self.entries: list[DiaryEntry] = []  # newest first
        self.index = 0

        self.persona_select: Select = Select(
            placeholder="選擇要閱讀日記的角色",
            options=[discord.SelectOption(label=p.name, value=str(p.id)) for p in personas],
        )
        self.persona_select.callback = self.on_select
        self.newer_button: Button = Button(
            label="較新", style=discord.ButtonStyle.primary, disabled=True
        )
        self.newer_button.callback = self.on_newer
        self.older_button: Button = Button(
            label="較舊", style=discord.ButtonStyle.primary, disabled=True
        )
        self.older_button.callback = self.on_older

        self.text: TextDisplay = TextDisplay("## 日記\n選擇角色開始閱讀")
        self.add_item(
            Container(
                self.text,
                ActionRow(self.persona_select),
                ActionRow(self.older_button, self.newer_button),
            )
        )

    def render(self) -> None:
        assert self.selected is not None
        if not self.entries:
            self.text.content = f"## {self.selected.name} 的日記\n這個角色還沒有寫過日記"
            self.older_button.disabled = True
            self.newer_button.disabled = True
            return

        entry = self.entries[self.index]
        content = entry.content
        if len(content) > DIARY_CONTENT_LIMIT:
            content = content[:DIARY_CONTENT_LIMIT] + "…"
        position = f"{self.index + 1}/{len(self.entries)}"
        self.text.content = (
            f"## {self.selected.name} 的日記\n### {entry.date.isoformat()} ({position})\n{content}"
        )
        self.newer_button.disabled = self.index == 0
        self.older_button.disabled = self.index == len(self.entries) - 1

    async def on_select(self, interaction: Interaction) -> None:
        selected_id = int(self.persona_select.values[0])
        self.selected = discord.utils.get(self.personas, id=selected_id)
        for option in self.persona_select.options:
            option.default = option.value == str(selected_id)
        self.entries = await DiaryEntry.filter(persona_id=selected_id).order_by("-date")
        self.index = 0
        self.render()
        await interaction.response.edit_message(view=self)

    async def on_newer(self, interaction: Interaction) -> None:
        self.index = max(self.index - 1, 0)
        self.render()
        await interaction.response.edit_message(view=self)

    async def on_older(self, interaction: Interaction) -> None:
        self.index = min(self.index + 1, len(self.entries) - 1)
        self.render()
        await interaction.response.edit_message(view=self)


class DiaryCog(commands.Cog):
    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @app_commands.command(name="diary", description="閱讀你的角色寫下的日記")
    @app_commands.guild_only()
    async def diary(self, i: Interaction) -> None:
        personas = await Persona.filter(discord_id=i.user.id, guild_id=i.guild_id).order_by(
            "created_at"
        )
        if not personas:
            embed = ErrorEmbed(title="尚未新增任何角色", description="先使用 `/waifus` 新增角色吧")
            await i.response.send_message(embed=embed, ephemeral=True)
            return
        await i.response.send_message(view=DiaryView(personas), ephemeral=True)

    @app_commands.command(name="diary-toggle", description="開啟或關閉角色的日記功能")
    @app_commands.guild_only()
    @app_commands.describe(persona="要設定的角色 (從清單中選擇)", enabled="是否啟用日記功能")
    async def diary_toggle(self, i: Interaction, persona: str, enabled: bool) -> None:
        selected = (
            await Persona.get_or_none(id=int(persona), discord_id=i.user.id)
            if persona.isdigit()
            else None
        )
        if selected is None:
            embed = ErrorEmbed(title="找不到角色", description="請從自動完成清單中選擇角色")
            await i.response.send_message(embed=embed, ephemeral=True)
            return
        selected.diary_enabled = enabled
        await selected.save(update_fields=["diary_enabled"])
        if enabled:
            embed = DefaultEmbed(
                title="日記功能已開啟", description=f"**{selected.name}** 會繼續撰寫與閱讀日記"
            )
        else:
            embed = DefaultEmbed(
                title="日記功能已關閉",
                description=(
                    f"**{selected.name}** 將不再撰寫或閱讀日記\n已寫下的日記仍可用 `/diary` 查看"
                ),
            )
        await i.response.send_message(embed=embed, ephemeral=True)

    @diary_toggle.autocomplete("persona")
    async def diary_toggle_autocomplete(
        self, i: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        personas = await Persona.filter(discord_id=i.user.id, guild_id=i.guild_id).order_by(
            "created_at"
        )
        return [
            app_commands.Choice(name=p.name, value=str(p.id))
            for p in personas
            if current.lower() in p.name.lower()
        ][:CHOICE_LIMIT]


async def setup(bot: MyBot) -> None:
    await bot.add_cog(DiaryCog(bot))
