import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
import os
import json


class EventForm(discord.ui.Modal, title="Creating an event"):
    def __init__(self, initInteraction: discord.Interaction):
        super().__init__()

        self.initChannel = initInteraction.channel
        self.linkedChannel = None
        self.rolePing = None

        # Confirm button
        self.confirmButton = discord.ui.Button(
            label="Confirm event", style=discord.ButtonStyle.success
        )

        self.confirmButton.callback = self._confirm_button

        self.pingModal = EventPingForm()

    name = discord.ui.TextInput(label="Event Name")
    description = discord.ui.TextInput(
        label="Event description", style=discord.TextStyle.long, required=False
    )
    date = discord.ui.TextInput(
        label="Date and Time (24hr Eastern)", placeholder="MM/DD/YYYY HH:MM"
    )
    duration = discord.ui.TextInput(label="Duration", placeholder="minutes")
    repeat = discord.ui.TextInput(label="Repeat every X days?", required=False)

    async def _confirm_button(self, interaction):
        await interaction.response.send_message(content="Event created!")
        await interaction.channel.edit(archived=True, locked=True)

        if self.linkedChannel is not None:
            event = await interaction.guild.create_scheduled_event(
                name=self.name.value,
                description=self.description.value,
                start_time=self.startTime,
                end_time=self.endTime,
                entity_type=discord.EntityType.voice,
                channel=self.linkedChannel,
            )
        else:
            event = await interaction.guild.create_scheduled_event(
                name=self.name.value,
                description=self.description.value,
                start_time=self.startTime,
                end_time=self.endTime,
                entity_type=discord.EntityType.external,
                location="Unknown",
            )

        # Write event to json
        with open("events.json", "r") as f:
            events = json.load(f)

        if not str(interaction.guild.id) in events.keys():
            events[str(interaction.guild.id)] = []
        eventDict = {
            "id": event.id,
            "name": self.name.value,
            "description": self.description.value,
            "startTime": self.startTime.timestamp(),
            "endTime": self.endTime.timestamp(),
            "channel": self.linkedChannel.id
            if self.linkedChannel is not None
            else None,
            "repeat": self.repeatDays,
            "repeated": False,
            "initChannel": self.initChannel.id,
            "rolePing": self.rolePing if self.rolePing is not None else None,
            "rolePingMinutes": int(self.pingModal.pingMinutes.value)
            if self.pingModal.pingMinutes.value is not None
            else None,
            "rolePingMessage": self.pingModal.pingMessage.value,
            "pinged": False,
            "interestPMMessage": "",
            "pmed": False,
        }
        events[str(interaction.guild.id)].append(eventDict)
        with open("events.json", "w") as f:
            json.dump(events, f)

    async def _channel_picker_changed(self, interaction):
        self.linkedChannel = discord.Object(interaction.data["values"][0])
        await interaction.response.defer()

    async def _role_picker_changed(self, interaction):
        self.rolePing = interaction.data["values"][0]
        await interaction.response.send_modal(self.pingModal)

    async def on_submit(self, interaction):
        # Parse inputs
        if not self.repeat.value == "":
            self.repeatDays = int(self.repeat.value)
        else:
            self.repeatDays = None
        self.startTime = datetime.datetime.strptime(
            self.date.value + "-0400", "%m/%d/%Y %H:%M%z"
        )
        self.endTime = self.startTime + datetime.timedelta(
            minutes=int(self.duration.value)
        )

        await interaction.response.send_message(
            f"Creating event: {self.name.value}"
        )
        self.optionThread = await interaction.channel.create_thread(
            name=f"Event options for {self.name.value}",
            message=interaction.channel.last_message,
            type=discord.ChannelType.public_thread,
            auto_archive_duration=60,
        )
        await self.optionThread.add_user(interaction.user)

        optionsView = discord.ui.View()
        # Channel picker
        channelPicker = discord.ui.Select(
            placeholder="Connect event to a channel...",
            options=[discord.SelectOption(label="None", value="none")],
        )
        for channel in interaction.guild.channels:
            if isinstance(channel, discord.VoiceChannel):
                channelPicker.append_option(
                    discord.SelectOption(label=channel.name, value=channel.id)
                )
        channelPicker.callback = self._channel_picker_changed
        optionsView.add_item(channelPicker)

        # Role ping picker
        rolePicker = discord.ui.Select(
            placeholder="Role to send a message to...",
            options=[discord.SelectOption(label="None", value="none")],
        )
        for role in interaction.guild.roles:
            rolePicker.append_option(
                discord.SelectOption(label=role.name, value=role.id)
            )
        rolePicker.callback = self._role_picker_changed
        optionsView.add_item(rolePicker)

        # Confirm button
        optionsView.add_item(self.confirmButton)

        await self.optionThread.send(content="Event options", view=optionsView)


class EventPingForm(discord.ui.Modal, title="Notification Options"):
    pingMessage = discord.ui.TextInput(
        label="Message to ping", style=discord.TextStyle.long, required=True
    )
    pingMinutes = discord.ui.TextInput(label="Ping X minutes before start")

    async def on_submit(self, interaction):
        # Checks if intable
        int(self.pingMinutes.value)
        await interaction.response.defer()


class EventManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

        # Check if events.json exists
        if not os.path.exists("events.json"):
            with open("events.json", "w") as f:
                f.write("{}")
        else:
            with open("events.json", "r") as f:
                self.events = json.load(f)

        self.check_events.start()

    @app_commands.command(name="create_event", description="Create an event.")
    async def createevent(self, interaction: discord.Interaction):
        await interaction.response.send_modal(
            EventForm(initInteraction=interaction)
        )

    @app_commands.command(name="delete_event", description="Delete an event.")
    async def deleteevent(self, interaction: discord.Interaction):
        # Get list of events managed by bot
        self._updateEvents()

        if str(interaction.guild.id) not in self.events.keys():
            await interaction.response.send_message(
                "No events are currently managed by this bot in this server.",
                ephemeral=True,
            )
        else:
            # Get list of events
            eventList = self.events[str(interaction.guild.id)]

            eventsView = discord.ui.View()
            # Channel picker
            eventPicker = discord.ui.Select(
                placeholder="Select event to delete...",
                options=[discord.SelectOption(label="None", value="none")],
            )
            for event in eventList:
                eventPicker.append_option(
                    discord.SelectOption(
                        label=event["name"], value=event["id"]
                    )
                )
            eventPicker.callback = self._delete_event
            eventsView.add_item(eventPicker)
            await interaction.response.send_message(
                view=eventsView, ephemeral=True
            )

    async def _delete_event(self, interaction):
        guildEvents = self.events[str(interaction.guild.id)]
        eventID = [
            event
            for event in guildEvents
            if str(event["id"]) == interaction.data["values"][0]
        ][0]["id"]

        # Update guild events to remove event
        guildEvents = [
            event for event in guildEvents if event["id"] != eventID
        ]
        self.events[str(interaction.guild.id)] = guildEvents

        # Save to json
        with open("events.json", "w") as f:
            f.write(json.dumps(self.events))

        # Delete event in Discord
        event = interaction.guild.get_scheduled_event(eventID)
        await event.delete()
        await interaction.response.send_message(
            "Event deleted.", ephemeral=True
        )
        await interaction.delete_original_message()

    def _updateEvents(self):
        with open("events.json", "r") as f:
            self.events = json.load(f)

    @tasks.loop(minutes=1)
    async def check_events(self):
        print("Checking events...")
        self._updateEvents()
        self.events

    @check_events.before_loop
    async def before_check_events(self):
        print("Waiting for bot to be ready to start events monitoring.")
        await self.bot.wait_until_ready()
