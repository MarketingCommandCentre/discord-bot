import discord
from src.model.Models import Request, RequestType, RequestStatus
from src.config.manager import BOT_CONFIG
from src.services.request_manager import RequestManager
from src.ui.views import SubgroupVisibilityView

class BaseRequestModal(discord.ui.Modal):
    request_manager: RequestManager

    def __init__(self, title: str, request_manager, guild: discord.Guild, existing_request: Request = None, request_type: RequestType = RequestType.POST):
        super().__init__(title=title)
        self.request_manager = request_manager
        self.guild = guild
        self.newRequest = existing_request is None
        if not existing_request:
            existing_request = Request(type=request_type)
        self.request = existing_request
        self.title_field = discord.ui.TextInput(
            label="Title",
            placeholder="Enter the title for your request...",
            max_length=BOT_CONFIG["max_request_title_length"],
            required=True,
            default=self.request.title if self.request.title else ""
        )
        self.add_item(self.title_field)
        
        self.description_field = discord.ui.TextInput(
            label="Description",
            placeholder="Provide details about what you need...",
            style=discord.TextStyle.paragraph,
            max_length=BOT_CONFIG["max_request_description_length"],
            required=True,
            default=self.request.description if self.request.description else ""
        )
        self.add_item(self.description_field)
        
        self.date_field = discord.ui.TextInput(
            label="Posting Date",
            placeholder="MM/DD/YYYY (e.g., 12/25/2024)",
            max_length=10,
            required=True,
            default=self.request.posting_date.strftime("%m/%d/%Y") if self.request.posting_date else ""
        )
        self.add_item(self.date_field)
        
        self.location_field = discord.ui.TextInput(
            label="Room/Location",
            placeholder="e.g., DV2082, Student Centre, Online Event, etc.",
            max_length=100,
            required=False,
            default=self.request.room if self.request.room else ""
        )
        self.add_item(self.location_field)
        
        self.signup_url_field = discord.ui.TextInput(
            label="Signup/Registration URL",
            placeholder="https://forms.gle/... or https://eventbrite.com/...",
            max_length=500,
            required=False,
            default=self.request.signup_url if self.request.signup_url else ""
        )
        self.add_item(self.signup_url_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle the modal submission."""
        self.request.title = self.title_field.value
        self.request.description = self.description_field.value
        self.request.room = self.location_field.value if self.location_field.value else None
        self.request.signup_url = self.signup_url_field.value if self.signup_url_field.value else None
        
        # Parse posting date
        from datetime import datetime
        try:
            self.request.posting_date = datetime.strptime(self.date_field.value, "%m/%d/%Y")
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid date format. Please use MM/DD/YYYY.",
                ephemeral=True
            )
            return
        
        # Set requester information
        self.request.requester_id = interaction.user.id
        
        # Defer the response immediately to avoid timeout (gives us 15 minutes instead of 3 seconds)
        await interaction.response.defer(ephemeral=True, thinking=True)
        
        try:
            if self.newRequest:
                # Create new request using request manager
                created_request = await self.request_manager.create_request(self.request, self.guild)
                if created_request:
                    await interaction.followup.send(
                        f"✅ Your {self.request.type.value} request has been created successfully! "
                        f"Check out your request channel: <#{created_request.channel_id}>",
                        ephemeral=True
                    )

                    if await self.request_manager.has_department_subgroups(self.request.requester_id):
                        dept_data = await self.request_manager.get_requester_department(self.request.requester_id)
                        subgroups = await self.request_manager.get_department_subgroups(self.request.requester_id)
                        
                        if dept_data and subgroups:
                            dept_id, dept_info = dept_data
                            view = SubgroupVisibilityView(
                                subgroups=subgroups,
                                department=dept_id,
                                request_manager=self.request_manager,
                                channel_id=created_request.channel_id
                            )
                            # Send the message in the new request channel
                            channel = interaction.guild.get_channel(created_request.channel_id)
                            if channel:
                                embed = discord.Embed(
                                    title="📋 Select Subgroup Visibility",
                                    description=f"<@{self.request.requester_id}> Please select which subgroup should have access to this request.",
                                    color=0x5865F2
                                )
                                embed.set_footer(text="Choose the appropriate visibility level for your department")
                                await channel.send(embed=embed, view=view)

                else:
                    await interaction.followup.send(
                        "❌ Failed to create request. Please try again.",
                        ephemeral=True
                    )
            else:
                # Update existing request using request manager
                updated_request = await self.request_manager.update_request(self.request)
                if updated_request:
                    await interaction.followup.send(
                        f"✅ Your {self.request.type.value} request has been updated successfully!",
                        ephemeral=True
                    )
                else:
                    await interaction.followup.send(
                        "❌ Failed to update request. Please try again.",
                        ephemeral=True
                    )
        except Exception as e:
            await interaction.followup.send(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )