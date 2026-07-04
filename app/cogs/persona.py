from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands

from app.core.embeds import ErrorEmbed
from app.db.models import Persona
from app.types import Interaction  # noqa: TC001
from app.ui import (
    ActionRow,
    Button,
    ChannelSelect,
    Container,
    Label,
    LayoutView,
    Modal,
    Select,
    TextDisplay,
    TextInput,
)

if TYPE_CHECKING:
    from app.core.bot import MyBot

MAX_PERSONAS_PER_GUILD = 25  # Discord select menu option limit


class PersonaModal(Modal):
    name: Label[TextInput] = Label(
        text="角色名字", component=TextInput(max_length=80, placeholder="例如: 小雪")
    )
    personality: Label[TextInput] = Label(
        text="角色個性", component=TextInput(style=discord.TextStyle.paragraph, max_length=4000)
    )
    facts: Label[TextInput] = Label(
        text="重要資訊",
        description="生日、喜好等重要事實 (選填)",
        component=TextInput(style=discord.TextStyle.paragraph, max_length=4000, required=False),
    )
    avatar_url: Label[TextInput] = Label(
        text="頭像網址",
        description="必須以 http(s):// 開頭 (選填)",
        component=TextInput(required=False, placeholder="https://..."),
    )
    channel: Label[ChannelSelect] = Label(
        text="頻道",
        description="角色綁定的頻道, 你在該頻道的訊息都會由這個角色回覆",
        component=ChannelSelect(channel_types=[discord.ChannelType.text], required=True),
    )

    def __init__(self, persona: Persona | None = None) -> None:
        super().__init__(title="編輯角色" if persona else "新增角色")
        self.persona = persona
        if persona is not None:
            self.name.component.default = persona.name
            self.personality.component.default = persona.personality
            self.facts.component.default = persona.facts
            self.avatar_url.component.default = persona.avatar_url
            self.channel.component.default_values = [
                discord.SelectDefaultValue(
                    id=persona.channel_id, type=discord.SelectDefaultValueType.channel
                )
            ]

    async def on_submit(self, i: Interaction) -> None:
        avatar_url = self.avatar_url.component.value.strip() or None
        if avatar_url is not None and not avatar_url.startswith(("http://", "https://")):
            embed = ErrorEmbed(title="無效的頭像網址", description="頭像網址必須以 http(s):// 開頭")
            await i.response.send_message(embed=embed, ephemeral=True)
            return

        channel_id = self.channel.component.values[0].id
        conflict = Persona.filter(discord_id=i.user.id, channel_id=channel_id)
        if self.persona is not None:
            conflict = conflict.exclude(id=self.persona.id)
        if await conflict.exists():
            embed = ErrorEmbed(
                title="頻道已被綁定",
                description="你在這個頻道已經有其他角色了, 請先刪除或改綁其他頻道",
            )
            await i.response.send_message(embed=embed, ephemeral=True)
            return

        fields = {
            "guild_id": i.guild_id,
            "channel_id": channel_id,
            "name": self.name.component.value.strip(),
            "personality": self.personality.component.value.strip(),
            "facts": self.facts.component.value.strip() or None,
            "avatar_url": avatar_url,
        }
        if self.persona is None:
            await Persona.create(discord_id=i.user.id, **fields)
        else:
            self.persona.update_from_dict(fields)
            await self.persona.save()

        await i.response.edit_message(view=await PersonaView.build(i))


class PersonaView(LayoutView):
    def __init__(self, personas: list[Persona]) -> None:
        super().__init__()
        self.personas = personas
        self.selected: Persona | None = None

        if personas:
            lines = "\n".join(f"- **{p.name}** <#{p.channel_id}>" for p in personas)
            body = f"## 你的角色\n{lines}"
        else:
            body = "## 你的角色\n尚未新增任何角色, 按下方按鈕開始"

        self.persona_select: Select = Select(
            placeholder="選擇要編輯或刪除的角色",
            options=[discord.SelectOption(label=p.name, value=str(p.id)) for p in personas],
        )
        self.persona_select.callback = self.on_select
        self.edit_button: Button = Button(
            label="編輯", style=discord.ButtonStyle.primary, disabled=True
        )
        self.edit_button.callback = self.on_edit
        self.delete_button: Button = Button(
            label="刪除", style=discord.ButtonStyle.danger, disabled=True
        )
        self.delete_button.callback = self.on_delete
        self.add_button: Button = Button(label="新增", style=discord.ButtonStyle.success)
        self.add_button.callback = self.on_add

        rows = (
            [
                ActionRow(self.persona_select),
                ActionRow(self.add_button, self.edit_button, self.delete_button),
            ]
            if personas
            else [ActionRow(self.add_button)]
        )
        self.add_item(Container(TextDisplay(body), *rows))

    @classmethod
    async def build(cls, i: Interaction) -> PersonaView:
        personas = await Persona.filter(discord_id=i.user.id, guild_id=i.guild_id).order_by(
            "created_at"
        )
        return cls(personas)

    async def on_select(self, interaction: Interaction) -> None:
        selected_id = int(self.persona_select.values[0])
        self.selected = discord.utils.get(self.personas, id=selected_id)
        self.edit_button.disabled = self.selected is None
        self.delete_button.disabled = self.selected is None
        for option in self.persona_select.options:
            option.default = option.value == str(selected_id)
        await interaction.response.edit_message(view=self)

    async def on_add(self, interaction: Interaction) -> None:
        count = await Persona.filter(
            discord_id=interaction.user.id, guild_id=interaction.guild_id
        ).count()
        if count >= MAX_PERSONAS_PER_GUILD:
            embed = ErrorEmbed(
                title="角色數量已達上限",
                description=f"每個伺服器最多 {MAX_PERSONAS_PER_GUILD} 個角色",
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return
        await interaction.response.send_modal(PersonaModal())

    async def on_edit(self, interaction: Interaction) -> None:
        if self.selected is None:
            return
        await interaction.response.send_modal(PersonaModal(self.selected))

    async def on_delete(self, interaction: Interaction) -> None:
        if self.selected is None:
            return
        await Persona.filter(id=self.selected.id).delete()
        await interaction.response.edit_message(view=await PersonaView.build(interaction))


class PersonaCog(commands.Cog):
    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @app_commands.command(name="waifus", description="管理你的專屬角色")
    @app_commands.guild_only()
    async def waifus(self, i: Interaction) -> None:
        await i.response.send_message(view=await PersonaView.build(i), ephemeral=True)


async def setup(bot: MyBot) -> None:
    await bot.add_cog(PersonaCog(bot))
