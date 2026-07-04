import datetime
import zoneinfo
from typing import TYPE_CHECKING

from discord import app_commands
from discord.ext import commands

from app.core.embeds import DefaultEmbed, ErrorEmbed
from app.db.models import Fact, ImportantDate
from app.services.memory import add_fact, add_important_date, get_or_create_user
from app.types import Interaction  # noqa: TC001

if TYPE_CHECKING:
    from app.core.bot import MyBot

CHOICE_NAME_LIMIT = 100  # Discord autocomplete choice name limit
CHOICE_LIMIT = 25  # Discord autocomplete choice count limit
FIELD_VALUE_LIMIT = 1024  # Discord embed field value limit

TIMEZONES = sorted(zoneinfo.available_timezones())


class ProfileCog(commands.Cog):
    me = app_commands.Group(name="me", description="管理你的個人資料 (所有角色都能看到)")

    def __init__(self, bot: MyBot) -> None:
        self.bot = bot

    @me.command(name="fact", description="新增一筆關於你的資訊 (喜好、居住地、習慣等)")
    @app_commands.describe(content="想讓角色記住的資訊, 例如: 我住在台北、我喜歡貓")
    async def me_fact(self, i: Interaction, content: str) -> None:
        user = await get_or_create_user(i.user.id)
        await add_fact(user, content)
        embed = DefaultEmbed(
            title="已記住",
            description=f"- {content}\n\n所有角色都會知道這件事\n使用 `/me show` 查看全部資料",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

    @me.command(name="date", description="新增一個重要日期 (生日、紀念日等)")
    @app_commands.describe(label="日期名稱, 例如: 生日", date="日期, 格式 YYYY-MM-DD")
    async def me_date(self, i: Interaction, label: str, date: str) -> None:
        try:
            parsed = datetime.date.fromisoformat(date)
        except ValueError:
            embed = ErrorEmbed(
                title="日期格式錯誤", description="請使用 YYYY-MM-DD 格式, 例如: 2000-01-31"
            )
            await i.response.send_message(embed=embed, ephemeral=True)
            return
        user = await get_or_create_user(i.user.id)
        await add_important_date(user, label, parsed)
        embed = DefaultEmbed(title="已記住", description=f"- {label}: {parsed.isoformat()}")
        await i.response.send_message(embed=embed, ephemeral=True)

    @me.command(name="timezone", description="設定你的時區 (影響提醒、問候與日記的時間)")
    @app_commands.describe(timezone="IANA 時區名稱, 例如: Asia/Taipei")
    async def me_timezone(self, i: Interaction, timezone: str) -> None:
        try:
            tz = zoneinfo.ZoneInfo(timezone)
        except zoneinfo.ZoneInfoNotFoundError, ValueError:
            embed = ErrorEmbed(
                title="無效的時區", description="請從自動完成清單中選擇, 例如: Asia/Taipei"
            )
            await i.response.send_message(embed=embed, ephemeral=True)
            return
        user = await get_or_create_user(i.user.id)
        user.timezone = timezone
        await user.save(update_fields=["timezone"])
        embed = DefaultEmbed(
            title="時區已設定",
            description=f"- {timezone}\n你的當地時間: {datetime.datetime.now(tz):%Y-%m-%d %H:%M}",
        )
        await i.response.send_message(embed=embed, ephemeral=True)

    @me_timezone.autocomplete("timezone")
    async def me_timezone_autocomplete(
        self, _: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        matches = [tz for tz in TIMEZONES if current.lower() in tz.lower()]
        return [app_commands.Choice(name=tz, value=tz) for tz in matches[:CHOICE_LIMIT]]

    @me.command(name="show", description="查看已儲存的個人資料")
    async def me_show(self, i: Interaction) -> None:
        facts = await Fact.filter(user__discord_id=i.user.id).order_by("created_at")
        dates = await ImportantDate.filter(user__discord_id=i.user.id).order_by("date")
        if not facts and not dates:
            embed = DefaultEmbed(
                title="沒有個人資料", description="使用 `/me fact` 或 `/me date` 新增"
            )
            await i.response.send_message(embed=embed, ephemeral=True)
            return

        embed = DefaultEmbed(title="你的個人資料")
        if facts:
            lines = "\n".join(f"- {fact.content}" for fact in facts)
            embed.add_field(
                name=f"資訊 ({len(facts)} 筆)", value=lines[:FIELD_VALUE_LIMIT], inline=False
            )
        if dates:
            lines = "\n".join(f"- {entry.label}: {entry.date.isoformat()}" for entry in dates)
            embed.add_field(
                name=f"重要日期 ({len(dates)} 筆)", value=lines[:FIELD_VALUE_LIMIT], inline=False
            )
        await i.response.send_message(embed=embed, ephemeral=True)

    @me.command(name="remove", description="刪除一筆個人資料")
    @app_commands.describe(item="要刪除的資料 (從清單中選擇)")
    async def me_remove(self, i: Interaction, item: str) -> None:
        kind, _, raw_id = item.partition(":")
        if kind == "fact" and raw_id.isdigit():
            deleted = await Fact.filter(id=int(raw_id), user__discord_id=i.user.id).delete()
        elif kind == "date" and raw_id.isdigit():
            deleted = await ImportantDate.filter(
                id=int(raw_id), user__discord_id=i.user.id
            ).delete()
        else:
            deleted = 0
        if deleted:
            embed = DefaultEmbed(title="已刪除", description="這筆資料已從你的個人資料中移除")
        else:
            embed = ErrorEmbed(title="找不到資料", description="請從自動完成清單中選擇要刪除的資料")
        await i.response.send_message(embed=embed, ephemeral=True)

    @me_remove.autocomplete("item")
    async def me_remove_autocomplete(
        self, i: Interaction, current: str
    ) -> list[app_commands.Choice[str]]:
        facts = await Fact.filter(user__discord_id=i.user.id).order_by("-created_at")
        dates = await ImportantDate.filter(user__discord_id=i.user.id).order_by("date")
        choices = [
            app_commands.Choice(name=fact.content[:CHOICE_NAME_LIMIT], value=f"fact:{fact.id}")
            for fact in facts
            if current.lower() in fact.content.lower()
        ] + [
            app_commands.Choice(
                name=f"{entry.label}: {entry.date.isoformat()}"[:CHOICE_NAME_LIMIT],
                value=f"date:{entry.id}",
            )
            for entry in dates
            if current.lower() in f"{entry.label}: {entry.date.isoformat()}".lower()
        ]
        return choices[:CHOICE_LIMIT]


async def setup(bot: MyBot) -> None:
    await bot.add_cog(ProfileCog(bot))
