import discord
from discord import app_commands
from discord.ext import commands
from typing import Literal, Optional, Union


class EventForm(discord.ui.Modal, title="Creating an event"):
    def __init__(self):
        super().__init__()

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
        label="Date and Time", placeholder="MM/DD/YYYY HH:MM"
    )
    duration = discord.ui.TextInput(label="Duration", placeholder="minutes")
    repeat = discord.ui.TextInput(label="Repeat every X days?", required=False)

    async def _confirm_button(self, interaction):
        await interaction.response.send_message(content="Event created!")
        await interaction.channel.edit(archived=True, locked=True)

    async def on_submit(self, interaction):
        await interaction.response.send_message(
            f"Creating event: {self.name.value}"
        )
        self.optionThread = await interaction.channel.create_thread(
            name=f"Event options",
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
            if isinstance(
                channel, (discord.TextChannel, discord.VoiceChannel)
            ):
                channelPicker.append_option(
                    discord.SelectOption(label=channel.name, value=channel.id)
                )
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
        optionsView.add_item(rolePicker)

        # Confirm button
        optionsView.add_item(self.confirmButton)

        await self.optionThread.send(content="Event options", view=optionsView)


class EventNotifyForm(discord.ui.Modal, title="Notification Options"):
    def __init__(self):
        super().__init__()

    # pingRole = discord.ui.Select(
    #     options=[
    #         discord.SelectOption(label='', value=None, default=True),
    #         discord.SelectOption(label='Everyone', value=None)
    #     ]
    # )
    pingRoleMinutes = discord.ui.TextInput(label="Ping X minutes before start")

    async def on_submit(self, interaction):
        await interaction.response.send_message(f"Creating the event!")


class EventManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="create_event", description="Create an event.")
    async def createevent(self, interaction: discord.Interaction):
        await interaction.response.send_modal(EventForm())
        # await interaction.response.send_message(
        #     f"Creating event {event_name} with the description {event_description}",
        #     ephemeral=True,
        # )
