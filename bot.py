import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime


class EventForm(discord.ui.Modal, title="Creating an event"):
    def __init__(self):
        super().__init__()

        self.linkedChannel = None
        self.initChannel = None
        self.rolePing = None

        # Confirm button
        self.confirmButton = discord.ui.Button(
            label="Confirm event", style=discord.ButtonStyle.success
        )

        self.confirmButton.callback = self._confirm_button

        self.notifyModal = EventNotifyForm()

    name = discord.ui.TextInput(label="Event Name")
    description = discord.ui.TextInput(
        label="Event description", style=discord.TextStyle.long, required=False
    )
    date = discord.ui.TextInput(
        label="Date and Time (Eastern)", placeholder="MM/DD/YYYY HH:MM"
    )
    duration = discord.ui.TextInput(label="Duration", placeholder="minutes")
    repeat = discord.ui.TextInput(label="Repeat every X days?", required=False)

    async def _confirm_button(self, interaction):
        await interaction.response.send_message(content="Event created!")
        await interaction.channel.edit(archived=True, locked=True)

        if self.linkedChannel is not None:
            await interaction.guild.create_scheduled_event(
                name=self.name.value,
                start_time=self.startTime,
                end_time=self.endTime,
                entity_type=discord.EntityType.voice,
                channel=self.linkedChannel,
            )
        else:
            await interaction.guild.create_scheduled_event(
                name=self.name.value,
                start_time=self.startTime,
                end_time=self.endTime,
                entity_type=discord.EntityType.external,
                location="Unknown",
            )

    async def _channel_picker_changed(self, interaction):
        self.linkedChannel = discord.Object(interaction.data["values"][0])
        await interaction.response.defer()

    async def _role_picker_changed(self, interaction):
        self.rolePing = interaction.data["values"][0]
        await interaction.response.defer()

    async def on_submit(self, interaction):
        # Parse inputs
        if not self.repeat.value == "":
            self.repeatDays = int(self.repeat.value)
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


class EventNotifyForm(discord.ui.Modal, title="Notification Options"):
    pingMessage = discord.ui.TextInput(
        label="Message to ping", style=discord.TextStyle.long, required=True
    )
    pingRoleMinutes = discord.ui.TextInput(label="Ping X minutes before start")

    async def on_submit(self, interaction):
        await interaction.response.defer()


class EventManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="create_event", description="Create an event.")
    async def createevent(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventForm())
