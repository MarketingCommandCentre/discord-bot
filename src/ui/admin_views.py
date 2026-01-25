"""
Admin UI components for the "god mode" request management.
Provides comprehensive editing capabilities for all request fields.
"""

import discord
from discord import ui
from datetime import datetime
from typing import Optional, List

from src.model.Models import Request, RequestStatus, RequestType
from src.services.request_manager import RequestManager
from src.config.manager import config


class AdminRequestManageView(ui.View):
    """
    Main admin view for managing a request with full control.
    Provides buttons to access different editing modals and actions.
    """
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager,
        guild: discord.Guild,
        timeout: float = 300
    ):
        super().__init__(timeout=timeout)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self._build_view()
    
    def _build_view(self):
        """Build the view with buttons for different actions."""
        # Row 1: Core editing buttons
        self.add_item(EditBasicInfoButton(self.request, self.request_manager, self.guild))
        self.add_item(EditStatusButton(self.request, self.request_manager, self.guild))
        self.add_item(EditTypeButton(self.request, self.request_manager, self.guild))
        
        # Row 2: Assignment and department buttons
        self.add_item(EditAssignmentButton(self.request, self.request_manager, self.guild))
        self.add_item(EditDepartmentButton(self.request, self.request_manager, self.guild))
        
        # Row 3: Channel and Danger zone
        self.add_item(EditChannelButton(self.request, self.request_manager, self.guild))
        self.add_item(RefreshButton(self.request, self.request_manager, self.guild))
        
        # Row 4: Save all changes / Danger zone
        self.add_item(DeleteRequestButton(self.request, self.request_manager, self.guild))
    
    def get_embed(self) -> discord.Embed:
        """Generate the main embed showing current request state."""
        embed = discord.Embed(
            title="🔧 Request Management Console",
            description=f"**God Mode** for request in <#{self.request.channel_id}>",
            color=0xFF6B35  # Orange for admin
        )
        
        # Basic Info Section
        embed.add_field(
            name="📋 Basic Information",
            value=(
                f"**Title:** {self.request.title or 'N/A'}\n"
                f"**Type:** {self.request.type.value if self.request.type else 'N/A'}\n"
                f"**Status:** {self.request.status.value.replace('_', ' ').title() if self.request.status else 'N/A'}"
            ),
            inline=False
        )
        
        # Description (truncated if long)
        desc = self.request.description or 'N/A'
        if len(desc) > 200:
            desc = desc[:197] + "..."
        embed.add_field(
            name="📝 Description",
            value=desc,
            inline=False
        )
        
        # Dates Section
        posting_date = self.request.posting_date.strftime("%m/%d/%Y") if self.request.posting_date else "Not set"
        created_at = self.request.created_at.strftime("%m/%d/%Y %H:%M") if self.request.created_at else "N/A"
        updated_at = self.request.updated_at.strftime("%m/%d/%Y %H:%M") if self.request.updated_at else "N/A"
        embed.add_field(
            name="📅 Dates",
            value=(
                f"**Posting Date:** {posting_date}\n"
                f"**Created:** {created_at}\n"
                f"**Updated:** {updated_at}"
            ),
            inline=True
        )
        
        # Location & URL Section
        embed.add_field(
            name="📍 Details",
            value=(
                f"**Room:** {self.request.room or 'N/A'}\n"
                f"**Signup URL:** {self.request.signup_url or 'N/A'}"
            ),
            inline=True
        )
        
        # Assignment Section
        requester = f"<@{self.request.requester_id}>" if self.request.requester_id else "N/A"
        assigned_to = f"<@{self.request.assigned_to_id}>" if self.request.assigned_to_id else "Unassigned"
        additional_role = f"<@&{self.request.additional_assignee_id}>" if self.request.additional_assignee_id else "None"
        embed.add_field(
            name="👥 People",
            value=(
                f"**Requester:** {requester}\n"
                f"**Assigned To:** {assigned_to}\n"
                f"**Add. Assignees Role:** {additional_role}"
            ),
            inline=False
        )
        
        # Department Section
        dept_role = f"<@&{self.request.requester_department_id}>" if self.request.requester_department_id else "N/A"
        embed.add_field(
            name="🏢 Department",
            value=f"**Department Role:** {dept_role}",
            inline=True
        )
        
        # IDs Section (for debugging)
        embed.add_field(
            name="🔢 IDs (Debug)",
            value=(
                f"**Channel ID:** `{self.request.channel_id}`\n"
                f"**Main Msg ID:** `{self.request.main_message_id or 'N/A'}`"
            ),
            inline=True
        )
        
        embed.set_footer(text="Use the buttons below to modify any field • Changes are saved immediately")
        embed.timestamp = datetime.now()
        
        return embed


class EditBasicInfoButton(ui.Button):
    """Button to edit basic info (title, description, dates, room, URL)."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Edit Basic Info",
            style=discord.ButtonStyle.primary,
            emoji="📋",
            row=0
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        modal = AdminBasicInfoModal(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_modal(modal)


class EditStatusButton(ui.Button):
    """Button to change request status."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Change Status",
            style=discord.ButtonStyle.secondary,
            emoji="🔄",
            row=0
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        view = StatusSelectView(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_message(
            "Select the new status for this request:",
            view=view,
            ephemeral=True
        )


class EditTypeButton(ui.Button):
    """Button to change request type."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Change Type",
            style=discord.ButtonStyle.secondary,
            emoji="📽️",
            row=0
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        view = TypeSelectView(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_message(
            "Select the new type for this request:",
            view=view,
            ephemeral=True
        )


class EditAssignmentButton(ui.Button):
    """Button to edit assignment fields."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Edit Assignments",
            style=discord.ButtonStyle.primary,
            emoji="👥",
            row=1
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        view = AssignmentSelectView(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_message(
            "Select what you want to modify:",
            view=view,
            ephemeral=True
        )


class EditDepartmentButton(ui.Button):
    """Button to edit department assignment."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Edit Department",
            style=discord.ButtonStyle.secondary,
            emoji="🏢",
            row=1
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        view = DepartmentSelectView(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_message(
            "Select the department for this request:",
            view=view,
            ephemeral=True
        )


class EditChannelButton(ui.Button):
    """Button to edit channel-related settings."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Channel Actions",
            style=discord.ButtonStyle.secondary,
            emoji="📺",
            row=2
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        view = ChannelActionsView(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_message(
            "Select a channel action:",
            view=view,
            ephemeral=True
        )


class RefreshButton(ui.Button):
    """Button to refresh the current view with latest data."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Refresh",
            style=discord.ButtonStyle.secondary,
            emoji="🔃",
            row=2
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        # Fetch fresh data from database
        fresh_request = await self.request_manager.get_request(self.request.channel_id)
        if fresh_request:
            self.view.request = fresh_request
            self.request = fresh_request
            # Update all buttons with fresh request
            for child in self.view.children:
                if hasattr(child, 'request'):
                    child.request = fresh_request
            await interaction.response.edit_message(embed=self.view.get_embed(), view=self.view)
        else:
            await interaction.response.send_message(
                "❌ Failed to refresh request data.",
                ephemeral=True
            )


class DeleteRequestButton(ui.Button):
    """Button to delete the request (danger zone)."""
    
    def __init__(self, request: Request, request_manager: RequestManager, guild: discord.Guild):
        super().__init__(
            label="Delete Request",
            style=discord.ButtonStyle.danger,
            emoji="🗑️",
            row=3
        )
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
    
    async def callback(self, interaction: discord.Interaction):
        view = DeleteConfirmView(self.request, self.request_manager, self.guild, self.view)
        await interaction.response.send_message(
            "⚠️ **Are you sure you want to delete this request?**\n"
            "This will delete the channel and all data. This action cannot be undone!",
            view=view,
            ephemeral=True
        )


# ============ MODALS ============

class AdminBasicInfoModal(ui.Modal):
    """Modal for editing basic request information."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(title="Edit Basic Information")
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
        
        self.title_field = ui.TextInput(
            label="Title",
            placeholder="Enter the title...",
            max_length=255,
            required=True,
            default=request.title or ""
        )
        self.add_item(self.title_field)
        
        self.description_field = ui.TextInput(
            label="Description",
            placeholder="Enter the description...",
            style=discord.TextStyle.paragraph,
            max_length=4000,
            required=False,
            default=request.description or ""
        )
        self.add_item(self.description_field)
        
        self.date_field = ui.TextInput(
            label="Posting Date (MM/DD/YYYY)",
            placeholder="MM/DD/YYYY",
            max_length=10,
            required=False,
            default=request.posting_date.strftime("%m/%d/%Y") if request.posting_date else ""
        )
        self.add_item(self.date_field)
        
        self.room_field = ui.TextInput(
            label="Room/Location",
            placeholder="e.g., DV2082, Online, etc.",
            max_length=100,
            required=False,
            default=request.room or ""
        )
        self.add_item(self.room_field)
        
        self.url_field = ui.TextInput(
            label="Signup/Registration URL",
            placeholder="https://...",
            max_length=500,
            required=False,
            default=request.signup_url or ""
        )
        self.add_item(self.url_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        # Update the request object
        self.request.title = self.title_field.value
        self.request.description = self.description_field.value or ""
        self.request.room = self.room_field.value if self.room_field.value else None
        self.request.signup_url = self.url_field.value if self.url_field.value else None
        
        # Parse date if provided
        if self.date_field.value:
            try:
                self.request.posting_date = datetime.strptime(self.date_field.value, "%m/%d/%Y")
            except ValueError:
                await interaction.response.send_message(
                    "❌ Invalid date format. Please use MM/DD/YYYY.",
                    ephemeral=True
                )
                return
        
        # Save to database
        updated = await self.request_manager.update_request(self.request)
        if updated:
            self.parent_view.request = updated
            # Update all buttons
            for child in self.parent_view.children:
                if hasattr(child, 'request'):
                    child.request = updated
            await interaction.response.edit_message(embed=self.parent_view.get_embed(), view=self.parent_view)
        else:
            await interaction.response.send_message(
                "❌ Failed to save changes.",
                ephemeral=True
            )


# ============ SELECT VIEWS ============

class StatusSelectView(ui.View):
    """View with dropdown to select request status."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(timeout=60)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
        
        options = [
            discord.SelectOption(
                label="In Queue",
                value=RequestStatus.IN_QUEUE.value,
                emoji="📥",
                default=request.status == RequestStatus.IN_QUEUE
            ),
            discord.SelectOption(
                label="In Progress",
                value=RequestStatus.IN_PROGRESS.value,
                emoji="🔄",
                default=request.status == RequestStatus.IN_PROGRESS
            ),
            discord.SelectOption(
                label="Awaiting Posting",
                value=RequestStatus.AWAITING_POSTING.value,
                emoji="⏳",
                default=request.status == RequestStatus.AWAITING_POSTING
            ),
            discord.SelectOption(
                label="Done",
                value=RequestStatus.DONE.value,
                emoji="✅",
                default=request.status == RequestStatus.DONE
            ),
            discord.SelectOption(
                label="Blocked",
                value=RequestStatus.BLOCKED.value,
                emoji="🚫",
                default=request.status == RequestStatus.BLOCKED
            ),
        ]
        
        self.select = ui.Select(
            placeholder="Select new status...",
            options=options
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        new_status = RequestStatus(self.select.values[0])
        
        # Update status and move channel
        updated = await self.request_manager.set_request_status(self.request.channel_id, new_status)
        
        if updated:
            self.parent_view.request = updated
            for child in self.parent_view.children:
                if hasattr(child, 'request'):
                    child.request = updated
            
            await interaction.response.edit_message(
                content=f"✅ Status changed to **{new_status.value.replace('_', ' ').title()}**",
                view=None
            )
            
            # Update the parent message
            try:
                await interaction.message.edit(embed=self.parent_view.get_embed(), view=self.parent_view)
            except:
                pass
        else:
            await interaction.response.edit_message(
                content="❌ Failed to change status.",
                view=None
            )


class TypeSelectView(ui.View):
    """View with buttons to select request type."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(timeout=60)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
        
        options = [
            discord.SelectOption(
                label="Post",
                value=RequestType.POST.value,
                emoji="📸",
                default=request.type == RequestType.POST
            ),
            discord.SelectOption(
                label="Reel",
                value=RequestType.REEL.value,
                emoji="📽️",
                default=request.type == RequestType.REEL
            ),
        ]
        
        self.select = ui.Select(
            placeholder="Select new type...",
            options=options
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        new_type = RequestType(self.select.values[0])
        self.request.type = new_type
        
        updated = await self.request_manager.update_request(self.request)
        
        if updated:
            self.parent_view.request = updated
            for child in self.parent_view.children:
                if hasattr(child, 'request'):
                    child.request = updated
            
            await interaction.response.edit_message(
                content=f"✅ Type changed to **{new_type.value.title()}**",
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Failed to change type.",
                view=None
            )


class AssignmentSelectView(ui.View):
    """View for assignment-related actions."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(timeout=60)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
    
    @ui.button(label="Change Requester", style=discord.ButtonStyle.primary, emoji="👤")
    async def change_requester(self, interaction: discord.Interaction, button: ui.Button):
        modal = ChangeUserModal(
            self.request, 
            self.request_manager, 
            self.guild, 
            self.parent_view,
            field="requester"
        )
        await interaction.response.send_modal(modal)
    
    @ui.button(label="Change Assignee", style=discord.ButtonStyle.primary, emoji="👷")
    async def change_assignee(self, interaction: discord.Interaction, button: ui.Button):
        modal = ChangeUserModal(
            self.request, 
            self.request_manager, 
            self.guild, 
            self.parent_view,
            field="assigned_to"
        )
        await interaction.response.send_modal(modal)
    
    @ui.button(label="Clear Assignee", style=discord.ButtonStyle.secondary, emoji="❌")
    async def clear_assignee(self, interaction: discord.Interaction, button: ui.Button):
        self.request.assigned_to_id = None
        updated = await self.request_manager.update_request(self.request)
        
        if updated:
            self.parent_view.request = updated
            for child in self.parent_view.children:
                if hasattr(child, 'request'):
                    child.request = updated
            await interaction.response.edit_message(
                content="✅ Assignee cleared.",
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Failed to clear assignee.",
                view=None
            )


class ChangeUserModal(ui.Modal):
    """Modal for changing user ID fields."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView,
        field: str
    ):
        super().__init__(title=f"Change {field.replace('_', ' ').title()}")
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
        self.field = field
        
        current_id = getattr(request, f"{field}_id", None)
        
        self.user_id_field = ui.TextInput(
            label="User ID (Discord ID)",
            placeholder="Enter the user's Discord ID...",
            max_length=20,
            required=True,
            default=str(current_id) if current_id else ""
        )
        self.add_item(self.user_id_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            user_id = int(self.user_id_field.value)
            
            # Verify user exists in guild
            member = self.guild.get_member(user_id)
            if not member:
                await interaction.response.send_message(
                    "❌ User not found in this server.",
                    ephemeral=True
                )
                return
            
            # Use specific endpoint for changing requester
            if self.field == "requester":
                updated = await self.request_manager.change_requester(self.request.channel_id, user_id)
            else:
                setattr(self.request, f"{self.field}_id", user_id)
                updated = await self.request_manager.update_request(self.request)
            
            if updated:
                self.parent_view.request = updated
                for child in self.parent_view.children:
                    if hasattr(child, 'request'):
                        child.request = updated
                await interaction.response.send_message(
                    f"✅ {self.field.replace('_', ' ').title()} changed to {member.mention}",
                    ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ Failed to save changes.",
                    ephemeral=True
                )
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid user ID format.",
                ephemeral=True
            )


class DepartmentSelectView(ui.View):
    """View for selecting department."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(timeout=60)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
        
        # Build options from configured departments
        departments = config.get("departments", {})
        subdepartments = config.get("department_subgroups", {})
        options = []
        
        # Add main departments
        for key, data in departments.items():
            role_id = data.get("role_id")
            if role_id:
                options.append(
                    discord.SelectOption(
                        label=data.get("name", key),
                        value=str(role_id),
                        default=request.requester_department_id == role_id
                    )
                )
        
        # Add subdepartments with parent indication
        for parent_key, subs in subdepartments.items():
            parent_data = departments.get(parent_key, {})
            parent_name = parent_data.get("name", parent_key)
            for sub_key, sub_data in subs.items():
                role_id = sub_data.get("role_id")
                if role_id:
                    options.append(
                        discord.SelectOption(
                            label=f"{sub_data.get('name', sub_key)} ({parent_name})",
                            value=str(role_id),
                            default=request.requester_department_id == role_id
                        )
                    )
        
        if not options:
            options.append(discord.SelectOption(label="No departments configured", value="0"))
        
        self.select = ui.Select(
            placeholder="Select department or subdepartment...",
            options=options[:25]  # Discord limit
        )
        self.select.callback = self.on_select
        self.add_item(self.select)
    
    async def on_select(self, interaction: discord.Interaction):
        dept_id = int(self.select.values[0])
        if dept_id == 0:
            await interaction.response.edit_message(
                content="❌ No departments configured.",
                view=None
            )
            return
        
        # Update department using the request manager
        updated = await self.request_manager.update_requester_department(self.request.channel_id, dept_id)
        
        if updated:
            self.parent_view.request = updated
            for child in self.parent_view.children:
                if hasattr(child, 'request'):
                    child.request = updated
            
            await interaction.response.edit_message(
                content=f"✅ Department changed to <@&{dept_id}>",
                view=None
            )
        else:
            await interaction.response.edit_message(
                content="❌ Failed to change department.",
                view=None
            )


class ChannelActionsView(ui.View):
    """View for channel-related actions."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(timeout=60)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
    
    @ui.button(label="Rename Channel", style=discord.ButtonStyle.primary, emoji="✏️")
    async def rename_channel(self, interaction: discord.Interaction, button: ui.Button):
        modal = RenameChannelModal(self.request, self.request_manager, self.guild, self.parent_view)
        await interaction.response.send_modal(modal)
    
    @ui.button(label="Sync Channel Permissions", style=discord.ButtonStyle.secondary, emoji="🔒")
    async def sync_permissions(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        channel = self.guild.get_channel(self.request.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await self.request_manager._calculate_permissions(self.request, channel, self.guild)
            await interaction.followup.send("✅ Channel permissions synced.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
    
    @ui.button(label="Rebuild Request Message", style=discord.ButtonStyle.secondary, emoji="📨")
    async def rebuild_message(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        channel = self.guild.get_channel(self.request.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await self.request_manager._update_request_message(self.request, channel)
            await interaction.followup.send("✅ Request message rebuilt.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)
    
    @ui.button(label="Move to Correct Category", style=discord.ButtonStyle.secondary, emoji="📁")
    async def move_category(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        channel = self.guild.get_channel(self.request.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            await self.request_manager._move_channel_to_category(self.request, channel)
            await interaction.followup.send("✅ Channel moved to correct category.", ephemeral=True)
        else:
            await interaction.followup.send("❌ Channel not found.", ephemeral=True)


class RenameChannelModal(ui.Modal):
    """Modal for renaming a channel."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(title="Rename Channel")
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
        
        channel = guild.get_channel(request.channel_id)
        current_name = channel.name if channel else ""
        
        self.name_field = ui.TextInput(
            label="New Channel Name",
            placeholder="Enter new channel name...",
            max_length=100,
            required=True,
            default=current_name
        )
        self.add_item(self.name_field)
    
    async def on_submit(self, interaction: discord.Interaction):
        channel = self.guild.get_channel(self.request.channel_id)
        if channel and isinstance(channel, discord.TextChannel):
            try:
                await channel.edit(name=self.name_field.value)
                await interaction.response.send_message(
                    f"✅ Channel renamed to **{self.name_field.value}**",
                    ephemeral=True
                )
            except discord.HTTPException as e:
                await interaction.response.send_message(
                    f"❌ Failed to rename channel: {e}",
                    ephemeral=True
                )
        else:
            await interaction.response.send_message(
                "❌ Channel not found.",
                ephemeral=True
            )


class DeleteConfirmView(ui.View):
    """Confirmation view for deleting a request."""
    
    def __init__(
        self, 
        request: Request, 
        request_manager: RequestManager, 
        guild: discord.Guild,
        parent_view: AdminRequestManageView
    ):
        super().__init__(timeout=30)
        self.request = request
        self.request_manager = request_manager
        self.guild = guild
        self.parent_view = parent_view
    
    @ui.button(label="Yes, Delete", style=discord.ButtonStyle.danger, emoji="🗑️")
    async def confirm_delete(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        
        try:
            # Delete from database first
            deleted = await self.request_manager.db.delete_request(self.request.channel_id)
            
            if deleted:
                # Then delete the channel
                channel = self.guild.get_channel(self.request.channel_id)
                if channel:
                    await channel.delete(reason=f"Request deleted by admin {interaction.user}")
                
                # Delete the additional assignee role if it exists
                if self.request.additional_assignee_id:
                    role = self.guild.get_role(self.request.additional_assignee_id)
                    if role:
                        try:
                            await role.delete(reason="Request deleted")
                        except:
                            pass
                
                await interaction.followup.send(
                    "✅ Request deleted successfully.",
                    ephemeral=True
                )
            else:
                await interaction.followup.send(
                    "❌ Failed to delete request from database.",
                    ephemeral=True
                )
        except Exception as e:
            await interaction.followup.send(
                f"❌ Error deleting request: {e}",
                ephemeral=True
            )
    
    @ui.button(label="Cancel", style=discord.ButtonStyle.secondary)
    async def cancel_delete(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(
            content="❌ Deletion cancelled.",
            view=None
        )
