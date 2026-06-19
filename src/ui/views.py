import discord

from src.services.request_manager import RequestManager
from src.model.Models import RequestType

class RequestView(discord.ui.View):
    def __init__(self, request_manager: RequestManager):
        super().__init__(timeout=None)  # Persistent view
        self.request_manager = request_manager
    
    @discord.ui.button(label="📸 Create Post Request", style=discord.ButtonStyle.primary, custom_id="persistent_post")
    async def post_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from src.ui.modals import BaseRequestModal
        modal = BaseRequestModal(
            title="Create Marketing Request", 
            request_manager=self.request_manager,
            request_type=RequestType.POST,
            guild=interaction.guild
        )
        await interaction.response.send_modal(modal)


    
    @discord.ui.button(label="📽️ Create Reel Request", style=discord.ButtonStyle.secondary, custom_id="persistent_reel")
    async def reel_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from src.ui.modals import BaseRequestModal
        modal = BaseRequestModal(
            title="Create Marketing Request",
            request_manager=self.request_manager,
            request_type=RequestType.REEL,
            guild=interaction.guild
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📷 Create Photography Request", style=discord.ButtonStyle.secondary, custom_id="persistent_photography")
    async def photography_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from src.ui.modals import BaseRequestModal
        modal = BaseRequestModal(
            title="Create Marketing Request",
            request_manager=self.request_manager,
            request_type=RequestType.PHOTOGRAPHY,
            guild=interaction.guild
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="🌐 Create Website Request", style=discord.ButtonStyle.secondary, custom_id="persistent_website")
    async def website_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from src.ui.modals import BaseRequestModal
        modal = BaseRequestModal(
            title="Create Marketing Request",
            request_manager=self.request_manager,
            request_type=RequestType.WEBSITE,
            guild=interaction.guild
        )
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="📋 Create Misc. Request", style=discord.ButtonStyle.secondary, custom_id="persistent_misc")
    async def misc_request(self, interaction: discord.Interaction, button: discord.ui.Button):
        from src.ui.modals import BaseRequestModal
        modal = BaseRequestModal(
            title="Create Marketing Request",
            request_manager=self.request_manager,
            request_type=RequestType.MISC,
            guild=interaction.guild
        )
        await interaction.response.send_modal(modal)

class RequestEditView(discord.ui.View):
    """View with edit button for request owners."""
    
    def __init__(self, requester_id: int, request_type: str, channel_id: int, request_manager: RequestManager = None):
        super().__init__(timeout=None)  # Persistent view
        self.requester_id = requester_id
        self.request_type = request_type
        self.channel_id = channel_id
        self.request_manager = request_manager

        # Dynamic unique custom_id per channel
        custom_id = f"edit_request:{channel_id}"
        button = discord.ui.Button(label="✏️ Edit Request", style=discord.ButtonStyle.secondary, custom_id=custom_id)
        button.callback = self._on_edit_click  # type: ignore
        self.add_item(button)

    async def _on_edit_click(self, interaction: discord.Interaction):
        """Handle edit button click."""

        # Fetch the request from the database to prefill the modal
        try:
            from src.client.database_client import DatabaseClient
            from src.model.Models import Request
            
            # Get the bot instance from the interaction
            bot = interaction.client
            db_client = getattr(bot, 'db', None)
            
            if not db_client:
                await interaction.response.send_message(
                    "❌ Database connection not available.",
                    ephemeral=True
                )
                return
            
            # Fetch the request from the database
            request = await db_client.get_request_by_channel_id(self.channel_id)
            
            if not request:
                await interaction.response.send_message(
                    "❌ Could not find request data.",
                    ephemeral=True
                )
                return
            
            # Get request manager if available
            request_manager = self.request_manager
            if not request_manager and hasattr(bot, 'get_cog'):
                request_cog = bot.get_cog('RequestCog')
                if request_cog:
                    request_manager = getattr(request_cog, 'request_manager', None)
            
            if not request_manager:
                await interaction.response.send_message(
                    "❌ Request manager not available.",
                    ephemeral=True
                )
                return
            
            # Open the edit modal with the existing request data
            from src.ui.modals import BaseRequestModal
            modal = BaseRequestModal(
                title="Edit Request",
                request_manager=request_manager,
                guild=interaction.guild,
                existing_request=request,
                request_type=request.type
            )
            await interaction.response.send_modal(modal)
            
        except Exception as e:
            await interaction.response.send_message(
                f"❌ An error occurred: {str(e)}",
                ephemeral=True
            )

class SubgroupVisibilityView(discord.ui.View):
    """Dynamic view for selecting department subgroup visibility"""
    
    def __init__(self, subgroups: dict, department: str, request_manager: RequestManager, channel_id: int, timeout: int = 300):
        super().__init__(timeout=timeout)
        self.subgroups = subgroups if subgroups else {}
        self.department = department
        self.request_manager = request_manager
        self.channel_id = channel_id
        self._build_buttons()
    
    def _build_buttons(self):
        """Build buttons dynamically based on department subgroups"""
        from src.config.manager import config
        
        # Add subgroup buttons
        for subgroup_key, subgroup_data in self.subgroups.items():
            name = subgroup_data.get("name", subgroup_key.title())
            emoji = self._get_emoji_for_subgroup(subgroup_key, name)
            
            button = discord.ui.Button(
                label=name,
                style=discord.ButtonStyle.primary,
                emoji=emoji,
                custom_id=f"subgroup_{subgroup_key}"
            )
            button.callback = self._create_subgroup_callback(subgroup_data, name)
            self.add_item(button)
        
        # Always add a "Everyone" button for full department visibility
        everyone_button = discord.ui.Button(
            label=f"🤝 Everyone ({self.department.title()})",
            style=discord.ButtonStyle.secondary,
            emoji="🤝",
            custom_id="everyone"
        )
        everyone_button.callback = self._create_everyone_callback()
        self.add_item(everyone_button)
    
    def _get_emoji_for_subgroup(self, subgroup_key: str, name: str) -> str:
        """Get appropriate emoji for subgroup based on naming patterns"""
        subgroup_lower = subgroup_key.lower()
        name_lower = name.lower()
        
        # Common patterns
        if "brother" in subgroup_lower or "brother" in name_lower:
            return "🧔‍♂️"
        elif "sister" in subgroup_lower or "sister" in name_lower:
            return "🧕"
        elif "marketing" in subgroup_lower or "marketing" in name_lower:
            return "📈"
        elif "design" in subgroup_lower or "design" in name_lower:
            return "🎨"
        elif "social" in subgroup_lower or "social" in name_lower:
            return "📱"
        else:
            return "👥"  
    
    def _create_subgroup_callback(self, subgroup_data: dict, display_name: str):
        """Create callback function for subgroup button"""
        async def callback(interaction: discord.Interaction):
            await self.request_manager.update_requester_department(interaction.channel.id, subgroup_data['role_id'])
            # Disable all the buttons in this view and update the original message
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            # Send a confirmation ephemerally
            await interaction.followup.send(f"✅ Visibility set to subgroup {display_name}", ephemeral=True)
        return callback
    
    def _create_everyone_callback(self):
        """Create callback function for everyone button"""
        async def callback(interaction: discord.Interaction):
            # Disable all the buttons in this view and update the original message
            for child in self.children:
                child.disabled = True
            await interaction.response.edit_message(view=self)
            # Send confirmation ephemerally
            await interaction.followup.send(
                f"✅ Visibility set to entire {self.department.title()} team.",
                ephemeral=True
            )
        return callback