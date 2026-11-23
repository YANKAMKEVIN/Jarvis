"""Live tools, family « files » : Fichiers, documents et presse-papiers.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def files_tools(self) -> dict:
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
        result = await asyncio.to_thread(self.files.list_files, path)
        self._debug_tool_result("list_files", result)
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
        result = await asyncio.to_thread(self.files.find_files, query, path)
        self._debug_tool_result("find_files", result)
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
        result = await asyncio.to_thread(self.files.search_content, query)
        self._debug_tool_result("search_files_by_content", result)
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
    @self._journaled("ask_about_document")
    async def ask_about_document(path: str, question: str) -> dict:
        """Answer a question about a local text document via the local model."""
        debug_live("tool_call", tool="ask_about_document")
        result = await asyncio.to_thread(self.document.ask, path, question)
        self._debug_tool_result("ask_about_document", result)
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
        result = await asyncio.to_thread(self.files.get_file_info, path)
        self._debug_tool_result("get_file_info", result)
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
    @self._journaled("open_file")
    @self._desktop_access
    async def open_file(path: str) -> dict:
        """Open a local file with macOS (scripts need a confirmation)."""
        debug_live("tool_call", tool="open_file", path=path)
        result = await asyncio.to_thread(self.files.open_file, path)
        self._debug_tool_result("open_file", result)

        if result.error_code != "script_needs_confirmation":
            return result.to_livekit_dict()

        def _executor():
            return self.files.open_file(path, allow_script=True)

        async with self.confirmation_lock:
            token = self.pending_actions.register("open_file", _executor)
        return ToolResult.success(
            "open_file",
            "Ce fichier est un script qui pourrait s'exécuter. Annonce-le a "
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
    @self._journaled("open_folder")
    @self._desktop_access
    async def open_folder(path: str) -> dict:
        """Open a local folder in Finder."""
        debug_live("tool_call", tool="open_folder", path=path)
        result = await asyncio.to_thread(self.files.open_folder, path)
        self._debug_tool_result("open_folder", result)
        return result.to_livekit_dict()

    @function_tool(
        name="create_folder",
        description=(
            "Cree un dossier local sans ecraser de chemin existant, puis "
            "verifie son existence."
        ),
    )
    @self._journaled("create_folder")
    @self._desktop_access
    async def create_folder(path: str) -> dict:
        """Create a local folder without overwriting."""
        debug_live("tool_call", tool="create_folder", path=path)
        result = await asyncio.to_thread(self.files.create_folder, path)
        self._debug_tool_result("create_folder", result)
        return result.to_livekit_dict()

    @function_tool(
        name="rename_file",
        description=(
            "Renomme un fichier ou dossier local sans ecraser une destination "
            "existante, puis verifie le resultat."
        ),
    )
    @self._journaled("rename_file")
    @self._desktop_access
    async def rename_file(path: str, new_name: str) -> dict:
        """Rename a local file or folder without overwriting."""
        debug_live(
            "tool_call",
            tool="rename_file",
            path=path,
            new_name=new_name,
        )
        result = await asyncio.to_thread(
            self.files.rename_file,
            path,
            new_name,
        )
        self._debug_tool_result("rename_file", result)
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
    @self._journaled("move_file")
    @self._desktop_access
    async def move_file(source: str, destination: str) -> dict:
        """Move a local file or folder without overwriting."""
        debug_live(
            "tool_call",
            tool="move_file",
            source=source,
            destination=destination,
        )
        result = await asyncio.to_thread(
            self.files.move_file,
            source,
            destination,
        )
        self._debug_tool_result("move_file", result)
        return result.to_livekit_dict()

    @function_tool(
        name="get_clipboard_text",
        description=(
            "Lit le texte actuellement disponible dans le presse-papiers "
            "du Mac. Utilise ce tool pour savoir ce qui a ete copie ou "
            "si le presse-papiers contient du texte."
        ),
    )
    @self._desktop_access
    async def get_clipboard_text() -> dict:
        """Read current readable text from the Mac clipboard."""
        debug_live("tool_call", tool="get_clipboard_text")
        async with self.clipboard_lock:
            result = await asyncio.to_thread(
                self.clipboard.get_clipboard_text,
            )
        self._debug_clipboard_result("get_clipboard_text", result)
        return result.to_livekit_dict()

    @function_tool(
        name="set_clipboard_text",
        description=(
            "Remplace le contenu texte du presse-papiers du Mac par le "
            "texte fourni, puis verifie que le texte relu est identique."
        ),
    )
    @self._desktop_access
    async def set_clipboard_text(text: str) -> dict:
        """Set Mac clipboard text and verify the result."""
        debug_live(
            "tool_call",
            tool="set_clipboard_text",
            length=len(text) if isinstance(text, str) else None,
        )
        async with self.clipboard_lock:
            result = await asyncio.to_thread(
                self.clipboard.set_clipboard_text,
                text,
            )
        self._debug_clipboard_result("set_clipboard_text", result)
        return result.to_livekit_dict()

    @function_tool(
        name="clear_clipboard",
        description=(
            "Efface le texte lisible du presse-papiers du Mac, puis "
            "verifie prudemment qu'aucun texte lisible n'est detecte."
        ),
    )
    @self._desktop_access
    async def clear_clipboard() -> dict:
        """Clear readable text from the Mac clipboard."""
        debug_live("tool_call", tool="clear_clipboard")
        async with self.clipboard_lock:
            result = await asyncio.to_thread(
                self.clipboard.clear_clipboard,
            )
        self._debug_clipboard_result("clear_clipboard", result)
        return result.to_livekit_dict()

    @function_tool(
        name="rewrite_clipboard",
        description=(
            "Transforme le texte actuellement dans le presse-papiers selon une "
            "instruction (reformuler, corriger les fautes, traduire, resumer, "
            "changer le ton) et remet le resultat dans le presse-papiers pour "
            "que l'utilisateur le colle : 'corrige ce que j'ai copie', 'traduis "
            "ca en anglais', 'reformule plus poliment'. instruction : ce qu'il "
            "faut faire du texte."
        ),
    )
    @self._journaled("rewrite_clipboard")
    @self._desktop_access
    async def rewrite_clipboard(instruction: str) -> dict:
        """Transform the clipboard text with the local model."""
        debug_live("tool_call", tool="rewrite_clipboard")
        async with self.clipboard_lock:
            result = await asyncio.to_thread(
                self.text_workshop.rewrite_clipboard, instruction,
            )
        self._debug_tool_result("rewrite_clipboard", result)
        return result.to_livekit_dict()

    return {
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
        "get_clipboard_text": get_clipboard_text,
        "set_clipboard_text": set_clipboard_text,
        "clear_clipboard": clear_clipboard,
        "rewrite_clipboard": rewrite_clipboard,
    }
