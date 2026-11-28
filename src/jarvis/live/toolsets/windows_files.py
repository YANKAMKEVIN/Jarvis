"""Window management and file tools.

Built by ``build(registry)``; ``jarvis.live.registry`` assembles every
toolset into the voice and planner tool lists.
"""
import asyncio
from typing import TYPE_CHECKING, Any

from livekit.agents import function_tool

from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live

if TYPE_CHECKING:
    from jarvis.live.registry import ToolRegistry


def build(registry: "ToolRegistry") -> dict[str, Any]:
    """Return this group's tools by name, bound to ``registry``."""
    @function_tool(
        name="get_active_window",
        description=(
            "Lit la fenetre active reelle du Mac : application, titre, "
            "position, taille, et etats minimise ou plein ecran."
        ),
    )
    @registry._desktop_access
    async def get_active_window() -> dict:
        """Read the currently active Mac window."""
        debug_live("tool_call", tool="get_active_window")
        result = await asyncio.to_thread(registry.windows.get_active_window)
        registry._debug_tool_result("get_active_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="focus_window",
        description=(
            "Met au premier plan une fenetre d'application macOS par nom "
            "d'application, puis verifie l'etat observe."
        ),
    )
    @registry._journaled("focus_window", "app_name")
    @registry._desktop_access
    async def focus_window(app_name: str) -> dict:
        """Focus a macOS application window."""
        debug_live("tool_call", tool="focus_window", app_name=app_name)
        result = await asyncio.to_thread(registry.windows.focus_window, app_name)
        registry._debug_tool_result("focus_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="minimize_window",
        description=(
            "Minimise la fenetre active, ou la fenetre d'une application "
            "si app_name est fourni, puis verifie l'etat observe."
        ),
    )
    @registry._journaled("minimize_window", "app_name")
    @registry._desktop_access
    async def minimize_window(app_name: str | None = None) -> dict:
        """Minimize the active window or an app window."""
        debug_live("tool_call", tool="minimize_window", app_name=app_name)
        result = await asyncio.to_thread(registry.windows.minimize_window, app_name)
        registry._debug_tool_result("minimize_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="maximize_window",
        description=(
            "Agrandit la fenetre active, ou la fenetre d'une application "
            "si app_name est fourni, dans le cadre utilisable sans activer "
            "le plein ecran macOS."
        ),
    )
    @registry._journaled("maximize_window", "app_name")
    @registry._desktop_access
    async def maximize_window(app_name: str | None = None) -> dict:
        """Maximize the active window or an app window without fullscreen."""
        debug_live("tool_call", tool="maximize_window", app_name=app_name)
        result = await asyncio.to_thread(registry.windows.maximize_window, app_name)
        registry._debug_tool_result("maximize_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="move_window",
        description=(
            "Deplace la fenetre active, ou la fenetre d'une application "
            "si app_name est fourni. position accepte uniquement left, "
            "right, center ou fullscreen."
        ),
    )
    @registry._journaled("move_window", "app_name")
    @registry._desktop_access
    async def move_window(position: str, app_name: str | None = None) -> dict:
        """Move the active window or an app window."""
        debug_live(
            "tool_call",
            tool="move_window",
            position=position,
            app_name=app_name,
        )
        result = await asyncio.to_thread(
            registry.windows.move_window,
            position,
            app_name,
        )
        registry._debug_tool_result("move_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="arrange_windows",
        description=(
            "Place deux applications cote a cote : la premiere sur la moitie "
            "gauche de l'ecran, la seconde sur la moitie droite ('mets Safari a "
            "gauche et Notes a droite', 'range ces deux fenetres'). left_app et "
            "right_app : les noms des applications."
        ),
    )
    @registry._desktop_access
    async def arrange_windows(left_app: str, right_app: str) -> dict:
        """Tile two apps side by side."""
        debug_live("tool_call", tool="arrange_windows")
        result = await asyncio.to_thread(
            registry.windows.arrange_side_by_side, left_app, right_app,
        )
        registry._debug_tool_result("arrange_windows", result)
        return result.to_livekit_dict()

    @function_tool(
        name="list_files",
        description=(
            "Liste les fichiers et dossiers d'un chemin local macOS. "
            "Utilise ce tool pour connaitre le contenu actuel d'un dossier."
        ),
    )
    async def list_files(path: str | None = None) -> dict:
        """List files in a local folder."""
        debug_live("tool_call", tool="list_files", path=path)
        result = await asyncio.to_thread(registry.files.list_files, path)
        registry._debug_tool_result("list_files", result)
        return result.to_livekit_dict()

    @function_tool(
        name="find_files",
        description=(
            "Recherche de maniere bornee des fichiers ou dossiers locaux "
            "par nom, correspondance partielle ou extension."
        ),
    )
    async def find_files(query: str, path: str | None = None) -> dict:
        """Find files or folders by name in a local folder."""
        debug_live("tool_call", tool="find_files", query=query, path=path)
        result = await asyncio.to_thread(registry.files.find_files, query, path)
        registry._debug_tool_result("find_files", result)
        return result.to_livekit_dict()

    @function_tool(
        name="search_files_by_content",
        description=(
            "Recherche des fichiers locaux par CONTENU ou metadonnees via "
            "Spotlight (rapide, tout le dossier personnel) : 'retrouve mon CV', "
            "'le document qui parle du budget 2026', 'la facture EDF'. Pour une "
            "recherche par nom de fichier precis dans un dossier, prefere "
            "find_files."
        ),
    )
    async def search_files_by_content(query: str) -> dict:
        """Spotlight content/metadata search across the home folder."""
        debug_live("tool_call", tool="search_files_by_content", query_length=len(query) if isinstance(query, str) else None)
        result = await asyncio.to_thread(registry.files.search_content, query)
        registry._debug_tool_result("search_files_by_content", result)
        return result.to_livekit_dict()

    @function_tool(
        name="ask_about_document",
        description=(
            "Lit un document texte local et repond a une question a son sujet : "
            "'resume ce fichier', 'que dit ce document sur le budget', 'quelles "
            "sont les dates dans ce contrat'. path : le chemin du fichier (utilise "
            "find_files ou search_files_by_content pour le retrouver d'abord si "
            "besoin). Fonctionne sur du texte (txt, md, code, csv) et les PDF. "
            "La reponse se base uniquement sur le contenu du document."
        ),
    )
    @registry._journaled("ask_about_document")
    async def ask_about_document(path: str, question: str) -> dict:
        """Answer a question about a local text document via the local model."""
        debug_live("tool_call", tool="ask_about_document")
        result = await asyncio.to_thread(registry.document.ask, path, question)
        registry._debug_tool_result("ask_about_document", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_file_info",
        description=(
            "Lit les informations actuelles d'un fichier ou dossier local : "
            "type, taille, date de modification et chemin absolu."
        ),
    )
    async def get_file_info(path: str) -> dict:
        """Read metadata for a local file or folder."""
        debug_live("tool_call", tool="get_file_info", path=path)
        result = await asyncio.to_thread(registry.files.get_file_info, path)
        registry._debug_tool_result("get_file_info", result)
        return result.to_livekit_dict()

    @function_tool(
        name="open_file",
        description=(
            "Ouvre un fichier local avec l'application macOS associee. "
            "Le chemin doit etre exact, idealement un chemin absolu retourne "
            "par un tool Files. Pour un script (.py, .rb, .pl, .php, .jar), "
            "rien n'est ouvert : renvoie un token et requires_confirmation ; "
            "annonce le fichier puis attends un oui clair avant "
            "confirm_action. Les executables sont refuses."
        ),
    )
    @registry._journaled("open_file")
    @registry._desktop_access
    async def open_file(path: str) -> dict:
        """Open a local file with macOS (scripts need a confirmation)."""
        debug_live("tool_call", tool="open_file", path=path)
        result = await asyncio.to_thread(registry.files.open_file, path)
        registry._debug_tool_result("open_file", result)

        if result.error_code != "script_needs_confirmation":
            return result.to_livekit_dict()

        def _executor():
            return registry.files.open_file(path, allow_script=True)

        async with registry.confirmation_lock:
            token = registry.pending_actions.register("open_file", _executor)
        return ToolResult.success(
            "open_file",
            "Ce fichier est un script qui pourrait s'executer. Annonce-le a "
            "l'utilisateur puis attends sa confirmation avant confirm_action.",
            requires_confirmation=True,
            token=token,
            **(result.data or {}),
        ).to_livekit_dict()

    @function_tool(
        name="open_folder",
        description=(
            "Ouvre un dossier local dans Finder. Le chemin doit etre exact, "
            "idealement un chemin absolu retourne par un tool Files."
        ),
    )
    @registry._journaled("open_folder")
    @registry._desktop_access
    async def open_folder(path: str) -> dict:
        """Open a local folder in Finder."""
        debug_live("tool_call", tool="open_folder", path=path)
        result = await asyncio.to_thread(registry.files.open_folder, path)
        registry._debug_tool_result("open_folder", result)
        return result.to_livekit_dict()

    @function_tool(
        name="create_folder",
        description=(
            "Cree un dossier local sans ecraser de chemin existant, puis "
            "verifie son existence."
        ),
    )
    @registry._journaled("create_folder")
    @registry._desktop_access
    async def create_folder(path: str) -> dict:
        """Create a local folder without overwriting."""
        debug_live("tool_call", tool="create_folder", path=path)
        result = await asyncio.to_thread(registry.files.create_folder, path)
        registry._debug_tool_result("create_folder", result)
        return result.to_livekit_dict()

    @function_tool(
        name="rename_file",
        description=(
            "Renomme un fichier ou dossier local sans ecraser une destination "
            "existante, puis verifie le resultat."
        ),
    )
    @registry._journaled("rename_file")
    @registry._desktop_access
    async def rename_file(path: str, new_name: str) -> dict:
        """Rename a local file or folder without overwriting."""
        debug_live(
            "tool_call",
            tool="rename_file",
            path=path,
            new_name=new_name,
        )
        result = await asyncio.to_thread(
            registry.files.rename_file,
            path,
            new_name,
        )
        registry._debug_tool_result("rename_file", result)
        return result.to_livekit_dict()

    @function_tool(
        name="move_file",
        description=(
            "Deplace un fichier ou dossier local sans jamais ecraser de "
            "chemin existant. destination est soit le chemin final exact, "
            "soit un dossier existant (par exemple Documents ou Bureau) : "
            "l'element y est alors place en gardant son nom."
        ),
    )
    @registry._journaled("move_file")
    @registry._desktop_access
    async def move_file(source: str, destination: str) -> dict:
        """Move a local file or folder without overwriting."""
        debug_live(
            "tool_call",
            tool="move_file",
            source=source,
            destination=destination,
        )
        result = await asyncio.to_thread(
            registry.files.move_file,
            source,
            destination,
        )
        registry._debug_tool_result("move_file", result)
        return result.to_livekit_dict()

    return {
        "get_active_window": get_active_window,
        "focus_window": focus_window,
        "minimize_window": minimize_window,
        "maximize_window": maximize_window,
        "move_window": move_window,
        "arrange_windows": arrange_windows,
        "list_files": list_files,
        "find_files": find_files,
        "search_files_by_content": search_files_by_content,
        "ask_about_document": ask_about_document,
        "get_file_info": get_file_info,
        "open_file": open_file,
        "open_folder": open_folder,
        "create_folder": create_folder,
        "rename_file": rename_file,
        "move_file": move_file,
    }
