import discord
from discord.ext import commands
from discord import app_commands
from supabase import create_client
import os
import uuid
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

PIX_KEY = os.getenv("PIX_KEY")
PIX_CITY = os.getenv("PIX_CITY")
PIX_NAME = os.getenv("PIX_NAME")

ADM_ROLE = "ADM"

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- PIX GENERATOR ---------------- #
def generate_pix(value, username):
    identifier = username.replace(" ", "")[:20]
    return f"""
PIX COPY-PASTE:
KEY: {PIX_KEY}
NAME: {PIX_NAME}
CITY: {PIX_CITY}
VALUE: R${value}
ID: {identifier}
"""

# ---------------- PAGINATION VIEW ---------------- #
class ProductView(discord.ui.View):
    def __init__(self, products, index=0):
        super().__init__(timeout=None)
        self.products = products
        self.index = index

    def get_embed(self):
        product = self.products[self.index]
        embed = discord.Embed(
            title=product['name'],
            description=product['description'],
            color=discord.Color.green()
        )
        embed.add_field(name="Preço", value=f"R${product['price']}")
        embed.set_image(url=product['image_url'])
        embed.set_footer(text=f"{self.index+1}/{len(self.products)}")
        return embed

    @discord.ui.button(label="⬅️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index - 1) % len(self.products)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        product = self.products[self.index]

        order_id = str(uuid.uuid4())

        supabase.table("orders").insert({
            "id": order_id,
            "user_id": str(interaction.user.id),
            "username": interaction.user.name,
            "product_id": product['id'],
            "status": "pending",
            "value": product['price']
        }).execute()

        thread = await interaction.channel.create_thread(
            name=f"pedido-{interaction.user.name}",
            type=discord.ChannelType.private_thread
        )

        pix = generate_pix(product['price'], interaction.user.name)

        await thread.send(f"""
🛒 **Novo Pedido**
Usuário: {interaction.user.mention}
Produto: {product['name']}
Valor: R${product['price']}

💳 **Pagamento via PIX**
{pix}
""")

        await interaction.response.send_message(
            "✅ Pedido criado! Verifique sua thread privada.",
            ephemeral=True
        )

    @discord.ui.button(label="➡️", style=discord.ButtonStyle.secondary)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.index = (self.index + 1) % len(self.products)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)


# ---------------- /comprar ---------------- #
@bot.tree.command(name="comprar", description="Comprar produtos")
async def comprar(interaction: discord.Interaction):
    products = supabase.table("products").select("*").execute().data

    if not products:
        await interaction.response.send_message("Nenhum produto disponível.", ephemeral=True)
        return

    view = ProductView(products)
    await interaction.response.send_message(embed=view.get_embed(), view=view)


# ---------------- ADMIN CHECK ---------------- #
def is_admin(user: discord.Member):
    return any(role.name == ADM_ROLE for role in user.roles)


# ---------------- /pedidos ---------------- #
@bot.tree.command(name="pedidos", description="Ver pedidos")
async def pedidos(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await interaction.response.send_message("Sem permissão.", ephemeral=True)

    orders = supabase.table("orders").select("*").eq("status", "pending").execute().data

    if not orders:
        return await interaction.response.send_message("Sem pedidos ativos.")

    order = orders[0]

    embed = discord.Embed(title="Pedido")
    embed.add_field(name="User", value=order['username'])
    embed.add_field(name="Valor", value=f"R${order['value']}")

    class OrderView(discord.ui.View):
        @discord.ui.button(label="Confirmar", style=discord.ButtonStyle.success)
        async def confirm(self, interaction2, button):
            supabase.table("orders").update({"status": "paid"}).eq("id", order['id']).execute()
            await interaction2.response.send_message("Pagamento confirmado!")

        @discord.ui.button(label="Cancelar", style=discord.ButtonStyle.danger)
        async def cancel(self, interaction2, button):
            supabase.table("orders").update({"status": "cancelled"}).eq("id", order['id']).execute()
            await interaction2.response.send_message("Pedido cancelado!")

    await interaction.response.send_message(embed=embed, view=OrderView())


# ---------------- /dashboard ---------------- #
@bot.tree.command(name="dashboard", description="Estatísticas")
async def dashboard(interaction: discord.Interaction):
    if not is_admin(interaction.user):
        return await interaction.response.send_message("Sem permissão.", ephemeral=True)

    orders = supabase.table("orders").select("*").execute().data

    total = sum(o['value'] for o in orders if o['status'] == "paid")
    count = len([o for o in orders if o['status'] == "paid"])

    embed = discord.Embed(title="📊 Dashboard")
    embed.add_field(name="Vendas", value=count)
    embed.add_field(name="Receita Total", value=f"R${total}")

    await interaction.response.send_message(embed=embed)


# ---------------- READY ---------------- #
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Bot online como {bot.user}")


bot.run(TOKEN)