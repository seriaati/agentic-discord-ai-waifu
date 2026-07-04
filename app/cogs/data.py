import datetime
import io
from typing import TYPE_CHECKING

import discord
import pydantic
from discord import app_commands
from discord.ext import commands

from app.cogs.persona import MAX_PERSONAS_PER_GUILD
from app.core.embeds import DefaultEmbed, ErrorEmbed
from app.db.models import DiaryEntry, Fact, ImportantDate, Observation, Persona
from app.services.memory import get_or_create_user
from app.types import Interaction  # noqa: TC001
from app.utils.misc import get_utc8_now

if TYPE_CHECKING:
    from app.core.bot import MyBot

EXPORT_VERSION = 1
IMPORT_MAX_FILE_SIZE = 10 * 1024 * 1024  # Discord bot upload limit; exports never exceed this


class DiaryEntryData(pydantic.BaseModel):
    date: datetime.date
    content: str
    created_at: datetime.datetime | None = None


class PersonaData(pydantic.BaseModel):
    guild_id: int
    channel_id: int
    name: str = pydantic.Field(max_length=80)
    avatar_url: str | None = None
    personality: str
    facts: str | None = None
    created_at: datetime.datetime | None = None
    diary_entries: list[DiaryEntryData] = pydantic.Field(default_factory=list)


class FactData(pydantic.BaseModel):
    content: str
    created_at: datetime.datetime | None = None


class ImportantDateData(pydantic.BaseModel):
    label: str = pydantic.Field(max_length=100)
    date: datetime.date
    created_at: datetime.datetime | None = None


class ObservationData(pydantic.BaseModel):
    kind: str = pydantic.Field(max_length=32)
    summary: str
    handled: bool = False
    created_at: datetime.datetime | None = None


class ExportData(pydantic.BaseModel):
    version: int
    exported_at: datetime.datetime | None = None
    personas: list[PersonaData] = pydantic.Field(default_factory=list)
    facts: list[FactData] = pydantic.Field(default_factory=list)
    important_dates: list[ImportantDateData] = pydantic.Field(default_factory=list)
    observations: list[ObservationData] = pydantic.Field(default_factory=list)


class DataCog(commands.Cog):
    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @app_commands.command(name="export", description="匯出你在機器人上的所有資料 (不含提醒)")
    async def export(self, i: Interaction) -> None:
        await i.response.defer(ephemeral=True)

        personas: list[PersonaData] = []
        for persona in await Persona.filter(discord_id=i.user.id).order_by("created_at"):
            entries = await DiaryEntry.filter(persona=persona).order_by("date")
            personas.append(
                PersonaData(
                    guild_id=persona.guild_id,
                    channel_id=persona.channel_id,
                    name=persona.name,
                    avatar_url=persona.avatar_url,
                    personality=persona.personality,
                    facts=persona.facts,
                    created_at=persona.created_at,
                    diary_entries=[
                        DiaryEntryData(date=e.date, content=e.content, created_at=e.created_at)
                        for e in entries
                    ],
                )
            )
        facts = await Fact.filter(user__discord_id=i.user.id).order_by("created_at")
        dates = await ImportantDate.filter(user__discord_id=i.user.id).order_by("date")
        observations = await Observation.filter(user__discord_id=i.user.id).order_by("created_at")

        data = ExportData(
            version=EXPORT_VERSION,
            exported_at=get_utc8_now(),
            personas=personas,
            facts=[FactData(content=f.content, created_at=f.created_at) for f in facts],
            important_dates=[
                ImportantDateData(label=d.label, date=d.date, created_at=d.created_at)
                for d in dates
            ],
            observations=[
                ObservationData(
                    kind=o.kind, summary=o.summary, handled=o.handled, created_at=o.created_at
                )
                for o in observations
            ],
        )

        diary_count = sum(len(p.diary_entries) for p in personas)
        embed = DefaultEmbed(
            title="匯出完成",
            description=(
                f"- 角色: {len(personas)} 筆\n"
                f"- 日記: {diary_count} 筆\n"
                f"- 資訊: {len(facts)} 筆\n"
                f"- 重要日期: {len(dates)} 筆\n"
                f"- 觀察紀錄: {len(observations)} 筆\n\n"
                "使用 `/import` 即可匯回這份檔案"
            ),
        )
        file = discord.File(
            io.BytesIO(data.model_dump_json(indent=2).encode()),
            filename=f"waifu-export-{get_utc8_now().date().isoformat()}.json",
        )
        await i.followup.send(embed=embed, file=file)

    @staticmethod
    async def _import_personas(
        discord_id: int, personas: list[PersonaData]
    ) -> tuple[int, int, int]:
        """Restore personas and their diary entries, returning (personas, diaries, skipped)."""
        imported = diaries = skipped = 0
        for p in personas:
            persona = await Persona.get_or_none(discord_id=discord_id, channel_id=p.channel_id)
            if persona is None:
                count = await Persona.filter(discord_id=discord_id, guild_id=p.guild_id).count()
                if count >= MAX_PERSONAS_PER_GUILD:
                    skipped += 1
                    continue
                persona = await Persona.create(
                    discord_id=discord_id,
                    guild_id=p.guild_id,
                    channel_id=p.channel_id,
                    name=p.name,
                    avatar_url=p.avatar_url,
                    personality=p.personality,
                    facts=p.facts,
                )
                imported += 1
            for entry in p.diary_entries:
                if not await DiaryEntry.filter(persona=persona, date=entry.date).exists():
                    await DiaryEntry.create(persona=persona, date=entry.date, content=entry.content)
                    diaries += 1
        return imported, diaries, skipped

    @app_commands.command(name="import", description="匯入之前用 /export 匯出的資料")
    @app_commands.describe(file="/export 產生的 JSON 檔案")
    async def import_(self, i: Interaction, file: discord.Attachment) -> None:
        if file.size > IMPORT_MAX_FILE_SIZE:
            embed = ErrorEmbed(title="檔案過大", description="匯入檔案不能超過 10 MB")
            await i.response.send_message(embed=embed, ephemeral=True)
            return

        await i.response.defer(ephemeral=True)
        try:
            data = ExportData.model_validate_json(await file.read())
        except pydantic.ValidationError:
            embed = ErrorEmbed(
                title="檔案格式錯誤", description="請上傳 `/export` 匯出的 JSON 檔案"
            )
            await i.followup.send(embed=embed)
            return
        if data.version != EXPORT_VERSION:
            embed = ErrorEmbed(
                title="不支援的檔案版本", description="這份檔案來自不相容的機器人版本"
            )
            await i.followup.send(embed=embed)
            return

        user = await get_or_create_user(i.user.id)
        imported_personas, imported_diaries, skipped_personas = await self._import_personas(
            i.user.id, data.personas
        )

        imported_facts = 0
        for f in data.facts:
            if not await Fact.filter(user=user, content=f.content).exists():
                await Fact.create(user=user, content=f.content)
                imported_facts += 1

        imported_dates = 0
        for d in data.important_dates:
            if not await ImportantDate.filter(user=user, label=d.label, date=d.date).exists():
                await ImportantDate.create(user=user, label=d.label, date=d.date)
                imported_dates += 1

        imported_observations = 0
        for o in data.observations:
            if not await Observation.filter(user=user, kind=o.kind, summary=o.summary).exists():
                await Observation.create(
                    user=user, kind=o.kind, summary=o.summary, handled=o.handled
                )
                imported_observations += 1

        description = (
            f"- 角色: {imported_personas} 筆\n"
            f"- 日記: {imported_diaries} 筆\n"
            f"- 資訊: {imported_facts} 筆\n"
            f"- 重要日期: {imported_dates} 筆\n"
            f"- 觀察紀錄: {imported_observations} 筆\n\n"
            "已存在的資料會自動略過"
        )
        if skipped_personas:
            description += f"\n有 {skipped_personas} 個角色因超過伺服器角色上限而未匯入"
        embed = DefaultEmbed(title="匯入完成", description=description)
        await i.followup.send(embed=embed)


async def setup(bot: MyBot) -> None:
    await bot.add_cog(DataCog(bot))
