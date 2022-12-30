import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import asyncio


class EventsView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.eventID = None

    @discord.ui.button(label="Done!", style=discord.ButtonStyle.green, row=4)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        """Turns off options and leaves the message as is without ui."""
        if self.eventID is not None:
            event = interaction.guild.get_scheduled_event(self.eventID)
            msg = event.url
            embed = EventDescription(event.description).create_embed()
        else:
            msg = "No event selected!"
            embed = None
        await interaction.response.edit_message(
            content=msg, embed=embed, view=None
        )
        self.stop()


class EventsDropdown(discord.ui.Select):
    """Dropdown to select available events from the guild."""

    def __init__(self):
        super().__init__(
            placeholder="Choose an event...",
            min_values=1,
            max_values=1,
            options=[],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        """When an event is selected, disable this dropdown and add the rest of the ui."""

        eventID = int(self.values[0])
        self.view.eventID = eventID
        event = interaction.guild.get_scheduled_event(eventID)
        desc = EventDescription(event.description)
        self.placeholder = event.name

        self.view.add_item(RepeatDropdown(eventID))
        self.view.add_item(MentionDropdown(eventID))
        self.view.add_item(MentionButton(eventID))

        self.disabled = True

        await interaction.response.edit_message(
            content=event.url, embed=desc.create_embed(), view=self.view
        )


class RepeatDropdown(discord.ui.Select):
    """Dropdown to select the repeat interval for the event."""

    def __init__(self, eventID: int):
        super().__init__(
            placeholder="Choose a repeat...",
            options=[
                discord.SelectOption(label="Never", value="never"),
                discord.SelectOption(label="Daily", value="daily"),
                discord.SelectOption(label="Weekly", value="weekly"),
                discord.SelectOption(label="Monthly", value="monthly"),
            ],
        )
        self.eventID = eventID

    async def callback(self, interaction: discord.Interaction):
        """When a repeat is selected, update the event and the message."""

        event = interaction.guild.get_scheduled_event(self.eventID)
        desc = EventDescription(event.description)
        await event.edit(
            description=desc.set_repeat(self.values[0]),
            channel=event.channel,
        )
        await interaction.response.edit_message(
            embed=desc.create_embed(), view=self.view
        )


class MentionDropdown(discord.ui.MentionableSelect):
    """
    Dropdown to select users and roles to ping in the channel that this command
    was invoked for the event
    """

    def __init__(self, eventID: int):
        super().__init__(
            placeholder="Ping users/roles...",
            min_values=0,
            max_values=25,
        )
        self.eventID = eventID

    async def callback(self, interaction: discord.Interaction):
        """When a mention is selected, update the event and the message."""
        event = interaction.guild.get_scheduled_event(self.eventID)
        desc = EventDescription(event.description)
        ids = []
        for ping in self.values:
            if isinstance(ping, discord.Role):
                ids.append("&" + str(ping.id))
            else:
                ids.append(str(ping.id))

        # Note the channel to ping is whichever channel this command was called
        desc = EventDescription(event.description)
        await event.edit(
            description=desc.set_mentions(ids, interaction.channel_id),
            channel=event.channel,
        )
        await interaction.response.edit_message(
            embed=desc.create_embed(), view=self.view
        )


class MentionButton(discord.ui.Button):
    """Button to remove all pings and the corresponding channel from the event."""

    def __init__(self, eventID: int):
        super().__init__(
            label="Remove pings", style=discord.ButtonStyle.secondary, row=4
        )
        self.eventID = eventID

    async def callback(self, interaction: discord.Interaction):
        """When the button is pressed, update the event and the message."""
        event = interaction.guild.get_scheduled_event(self.eventID)
        desc = EventDescription(event.description)
        await event.edit(
            description=desc.set_mentions([], interaction.channel_id),
            channel=event.channel,
        )
        await interaction.response.edit_message(
            view=self.view, embed=desc.create_embed()
        )


class EventDescription:
    """
    Class to parse and handle descriptions with event parameters potentially
    encoded inside.
    """

    def __init__(self, description: str):
        self.header = "#!raided"

        # Check if description has header
        if description is not None:
            description = description.split(self.header)
        else:
            description = [""]

        self.description = description[0].rstrip()
        self.params = {
            "repeat": None,
            "mentions": None,
            "channel": None,
        }
        if len(description) == 2:
            # Split params and fill in dictionary
            params = description[1].split("\n")
            for param in params:
                if param.startswith("#repeat="):
                    self.params["repeat"] = param.split("=")[1]
                elif param.startswith("#mentions="):
                    self.params["mentions"] = param.split("=")[1]
                elif param.startswith("#channel="):
                    self.params["channel"] = int(param.split("=")[1])

    def set_repeat(self, repeat: str) -> str:
        """Set the repeat parameter and return the new description for convenience"""
        if repeat not in ["never", "daily", "weekly", "monthly"]:
            raise ValueError(
                "Repeat must be one of 'never', 'daily', 'weekly', 'monthly'"
            )

        self.params["repeat"] = repeat if repeat != "never" else None
        return str(self)

    def set_mentions(self, mentions: list, channel: int) -> str:
        """Set the mentions and channel parameters and return the new description for convenience"""
        if len(mentions) == 0:
            self.params["mentions"] = None
            self.params["channel"] = None
        else:
            self.params["mentions"] = ",".join(mentions)
            self.params["channel"] = channel

        return str(self)

    def create_embed(self) -> discord.Embed:
        """Return an embed with the event parameters as fields"""
        # Create embed
        embed = discord.Embed(title="Raided Event Options", type="rich")

        repeat = self.params["repeat"]
        repeat = repeat if repeat is not None else "Never"
        embed.add_field(name="Repeat", value=repeat.capitalize(), inline=False)

        mentions = self.params["mentions"]
        if mentions is not None:
            mentions = mentions.split(",")
            mentions = [f"<@{mention}>" for mention in mentions]
            mentions = "".join(mentions)
        else:
            mentions = "None"
        embed.add_field(name="Ping", value=mentions, inline=False)

        channel = self.params["channel"]
        channel = f"<#{channel}>" if channel is not None else "None"
        embed.add_field(name="Channel", value=channel, inline=False)

        embed.set_footer(
            text="Change the ping channel by setting pings in another channel."
        )

        return embed

    def __str__(self) -> str:
        """Return the description with the parameters encoded inside"""
        description = self.description
        params = f"\n\n\n\n\n{self.header}\n"
        for key, value in self.params.items():
            if value is not None:
                params += f"#{key}={value}\n"
        if not params.endswith(f"{self.header}\n"):
            description += params

        return description


class EventManager(commands.GroupCog, group_name="events"):
    """Main cog for the event manager module."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.tree = bot.tree
        self.check_events.start()

    def cog_unload(self):
        # Important to stop event checker if cog is unloaded
        self.check_events.cancel()

    @app_commands.command(name="edit", description="Edit an event.")
    @app_commands.default_permissions(manage_events=True)
    async def editevent(self, interaction: discord.Interaction):
        # This event also acts as the command to determine if this module is loaded
        events = interaction.guild.scheduled_events

        if len(events) == 0:
            await interaction.response.send_message(
                "There are no events to edit, make an event using Discord.",
                ephemeral=True,
            )
            return
        else:
            events = {event.id: event.name for event in events}

        eventsView = EventsView()
        # Channel picker
        eventPicker = EventsDropdown()
        for eventID, eventName in events.items():
            eventPicker.append_option(
                discord.SelectOption(label=eventName, value=eventID)
            )
        eventsView.add_item(eventPicker)

        await interaction.response.send_message(
            view=eventsView, ephemeral=True
        )

    @tasks.loop(minutes=1)
    async def check_events(self):
        """Check events to create repeats, ping, or start."""
        now = datetime.datetime.utcnow()
        now = now.strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{now}] Checking events...")
        for guild in self.bot.guilds:
            # Only check further if the guild has events module loaded
            if not self.bot.tree.get_command("edit", guild=guild):
                continue

            # Check events of a guild
            for event in guild.scheduled_events:
                # Check if they're managed by raided
                if (
                    event.description is not None
                    and "#!raided" in event.description
                ):
                    desc = EventDescription(event.description)
                    if desc.params["repeat"] is not None:
                        # Check if event is about to start
                        if event.start_time - datetime.timedelta(
                            minutes=5
                        ) < datetime.datetime.now(datetime.timezone.utc):
                            # Calculate new start time based on repeat
                            if desc.params["repeat"] == "daily":
                                newStart = (
                                    event.start_time
                                    + datetime.timedelta(days=1)
                                )
                            elif desc.params["repeat"] == "weekly":
                                newStart = (
                                    event.start_time
                                    + datetime.timedelta(weeks=1)
                                )
                            elif desc.params["repeat"] == "monthly":
                                newStart = (
                                    event.start_time
                                    + datetime.timedelta(months=1)
                                )
                            # Schedule event
                            await guild.create_scheduled_event(
                                name=event.name,
                                description=str(desc),
                                channel=event.channel,
                                start_time=newStart,
                                end_time=newStart
                                + datetime.timedelta(hours=1),
                            )

                            # Remove repeat from old event
                            await event.edit(
                                description=desc.set_repeat("never"),
                                channel=event.channel,
                            )

                    # Check if event should start
                    if (
                        event.status is discord.EventStatus.scheduled
                        and event.start_time
                        < datetime.datetime.now(datetime.timezone.utc)
                    ):
                        # Get mentions
                        mentions = []
                        if desc.params["mentions"] is not None:
                            mentions = desc.params["mentions"].split(",")
                            mentions = [
                                f"<@{mention}>" for mention in mentions
                            ]
                            # Get channel
                            channel = guild.get_channel(desc.params["channel"])

                            # Send message
                            await channel.send(
                                f"{''.join(mentions)} {event.name} is starting!"
                            )

                        # Start event
                        await event.start()

    @check_events.before_loop
    async def before_check_events(self):
        print("Waiting for bot to be ready to start events monitoring.")
        await self.bot.wait_until_ready()

        # Set the time to start
        now = datetime.datetime.utcnow()
        nextMinute = now + datetime.timedelta(minutes=1)
        nextMinute = nextMinute.replace(second=1, microsecond=0)
        waitSecs = (nextMinute - now).total_seconds()
        print(f"Waiting {waitSecs} seconds to start events monitoring.")
        await asyncio.sleep(waitSecs)

    async def cog_app_command_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        if isinstance(error, app_commands.errors.MissingPermissions):
            await interaction.response.send_message(
                "You don't have permissions to use this command.",
                ephemeral=True,
            )
        await interaction.response.send_message(
            "Unknown error!", ephemeral=True
        )


async def setup(bot):
    await bot.add_cog(EventManager(bot))

    # Remove commands from global, important for modular bot
    bot.tree.remove_command("events")


async def teardown(bot):
    await bot.remove_cog("EventManager")
