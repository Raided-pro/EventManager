import discord
from discord import app_commands
from discord.ext import commands, tasks
import os
import json
import datetime


class EventsView(discord.ui.View):
    def __init__(self):
        super().__init__()
        self.eventID = None

    @discord.ui.button(label="Done!", style=discord.ButtonStyle.green, row=4)
    async def confirm(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if self.eventID is not None:
            msg = interaction.guild.get_scheduled_event(self.eventID).url
        else:
            msg = "No event selected!"
        await interaction.response.edit_message(content=msg, view=None)
        self.stop()


class EventsDropdown(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="Choose an event...",
            min_values=1,
            max_values=1,
            options=[],
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        # Get event info
        eventID = int(self.values[0])
        self.view.eventID = eventID
        event = interaction.guild.get_scheduled_event(eventID)
        self.placeholder = event.name

        self.view.add_item(RepeatDropdown(eventID))
        self.view.add_item(MentionDropdown(eventID))
        self.view.add_item(MentionButton(eventID))

        self.disabled = True
        await interaction.response.edit_message(
            content=event.url, view=self.view
        )


class RepeatDropdown(discord.ui.Select):
    def __init__(self, eventID):
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
        # Get event info
        event = interaction.guild.get_scheduled_event(self.eventID)
        desc = EventDescription(event.description)
        await event.edit(
            description=desc.set_repeat(self.values[0]), channel=event.channel
        )
        await interaction.response.edit_message(view=self.view)


class MentionDropdown(discord.ui.MentionableSelect):
    def __init__(self, eventID):
        super().__init__(
            placeholder="Ping users/roles...",
            min_values=0,
            max_values=25,
        )
        self.eventID = eventID

    async def callback(self, interaction: discord.Interaction):
        # Get event info
        event = interaction.guild.get_scheduled_event(self.eventID)
        ids = []
        for ping in self.values:
            if isinstance(ping, discord.Role):
                ids.append("&" + str(ping.id))
            else:
                ids.append(str(ping.id))

        desc = EventDescription(event.description)
        await event.edit(
            description=desc.set_mentions(ids, interaction.channel_id),
            channel=event.channel,
        )
        await interaction.response.edit_message(view=self.view)


class MentionButton(discord.ui.Button):
    def __init__(self, eventID):
        super().__init__(
            label="Remove pings",
            style=discord.ButtonStyle.secondary,
        )
        self.eventID = eventID

    async def callback(self, interaction: discord.Interaction):
        # Get event info
        event = interaction.guild.get_scheduled_event(self.eventID)
        desc = EventDescription(event.description)
        await event.edit(
            description=desc.set_mentions([], interaction.channel_id),
            channel=event.channel,
        )
        await interaction.response.edit_message(view=self.view)


class EventDescription:
    def __init__(self, description) -> None:
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

    def set_repeat(self, repeat: str):
        if repeat not in ["never", "daily", "weekly", "monthly"]:
            raise ValueError(
                "Repeat must be one of 'never', 'daily', 'weekly', 'monthly'"
            )

        self.params["repeat"] = repeat if repeat != "never" else None
        return str(self)

    def set_mentions(self, mentions: list, channel: int):
        if len(mentions) == 0:
            self.params["mentions"] = None
            self.params["channel"] = None
        else:
            self.params["mentions"] = ",".join(mentions)
            self.params["channel"] = channel

        return str(self)

    def __str__(self) -> str:
        description = self.description
        params = f"\n\n\n\n\n{self.header}\n"
        for key, value in self.params.items():
            if value is not None:
                params += f"#{key}={value}\n"
        if not params.endswith(f"{self.header}\n"):
            description += params

        return description


class EventManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        self.check_events.start()

    @app_commands.command(name="edit_events", description="Edit an event.")
    @app_commands.checks.has_permissions(manage_events=True)
    async def editevent(self, interaction: discord.Interaction):
        events = interaction.guild.scheduled_events
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
        print("Checking events...")
        for guild in self.bot.guilds:
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
