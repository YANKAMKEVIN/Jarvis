"""Live tools, family « web » : Navigateur, captures d’écran, vision et recherche web.

Part of ToolRegistry.livekit_tools(): `self` is the registry; tools keep its
locks, journal, pending-action store and read-only guard.
"""
from jarvis.capabilities.results import ToolResult
from jarvis.live.config import debug_live
from livekit.agents import function_tool
import asyncio


def web_tools(self) -> dict:
    @function_tool(
        name="browse_open_url",
        description=(
            "Ouvre une URL dans Safari ou Google Chrome, active la fenetre "
            "puis relit l'onglet actif pour verifier le chargement. Utilise "
            "ce tool pour aller sur un site. browser=None choisit "
            "automatiquement le navigateur ouvert (Safari par defaut). "
            "new_tab=true ouvre un nouvel onglet, false reutilise l'onglet "
            "actif. state_confirmed=true seulement si l'onglet actif pointe "
            "bien vers le domaine demande."
        ),
    )
    @self._journaled("browse_open_url", "url", self._journal_host)
    @self._desktop_access
    async def browse_open_url(
        url: str,
        browser: str | None = None,
        new_tab: bool = True,
    ) -> dict:
        """Open a URL in a browser and verify the active tab."""
        debug_live(
            "tool_call",
            tool="browse_open_url",
            browser=browser,
            new_tab=new_tab,
        )
        async with self.browser_lock:
            result = await asyncio.to_thread(
                self.browser.open_url,
                url,
                browser,
                new_tab,
            )
        self._debug_browser_result("browse_open_url", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_search_web",
        description=(
            "Lance une recherche web dans Safari ou Google Chrome puis relit "
            "l'onglet actif pour verifier. Utilise ce tool pour une demande "
            "comme cherche la meteo. engine accepte google, duckduckgo ou "
            "bing (google par defaut). command_executed ne prouve pas que les "
            "resultats sont charges ; state_confirmed le fait."
        ),
    )
    @self._journaled("browse_search_web")
    @self._desktop_access
    async def browse_search_web(
        query: str,
        browser: str | None = None,
        engine: str | None = None,
    ) -> dict:
        """Run a web search in a browser and verify the active tab."""
        debug_live(
            "tool_call",
            tool="browse_search_web",
            browser=browser,
            engine=engine,
            query_length=len(query) if isinstance(query, str) else None,
        )
        async with self.browser_lock:
            result = await asyncio.to_thread(
                self.browser.search_web,
                query,
                browser,
                engine,
            )
        self._debug_browser_result("browse_search_web", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_get_active_tab",
        description=(
            "Lit l'onglet actif (URL et titre) de Safari ou Google Chrome. "
            "Utilise ce tool pour savoir quelle page est affichee au lieu de "
            "le deduire. browser=None choisit automatiquement le navigateur."
        ),
    )
    @self._desktop_access
    async def browse_get_active_tab(browser: str | None = None) -> dict:
        """Read the active tab of a browser."""
        debug_live("tool_call", tool="browse_get_active_tab", browser=browser)
        async with self.browser_lock:
            result = await asyncio.to_thread(
                self.browser.get_active_tab,
                browser,
            )
        self._debug_browser_result("browse_get_active_tab", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_list_tabs",
        description=(
            "Liste les onglets ouverts (index, URL, titre) de la fenetre "
            "active de Safari ou Google Chrome. Utile avant d'activer un "
            "onglet precis. browser=None choisit automatiquement."
        ),
    )
    @self._desktop_access
    async def browse_list_tabs(browser: str | None = None) -> dict:
        """List the tabs of a browser's front window."""
        debug_live("tool_call", tool="browse_list_tabs", browser=browser)
        async with self.browser_lock:
            result = await asyncio.to_thread(
                self.browser.list_tabs,
                browser,
            )
        self._debug_browser_result("browse_list_tabs", result)
        return result.to_livekit_dict()

    @function_tool(
        name="browse_activate_tab",
        description=(
            "Active un onglet dans Safari ou Google Chrome, puis verifie "
            "qu'il est au premier plan. Deux modes exclusifs : fournis index, "
            "un entier (position de l'onglet telle que donnee par "
            "browse_list_tabs), pour l'activer directement et de maniere "
            "deterministe ; OU fournis query (texte) pour une recherche sur "
            "l'URL ou le titre. Quand l'utilisateur choisit explicitement un "
            "onglet par son numero ou sa position (par exemple le 8), utilise "
            "index, jamais query. Si query correspond a plusieurs onglets, le "
            "resultat est ambiguous_tab : ne choisis pas au hasard, relis "
            "browse_list_tabs et rappelle ce tool avec l'index voulu. "
            "browser=None choisit automatiquement."
        ),
    )
    @self._desktop_access
    async def browse_activate_tab(
        query: str | None = None,
        index: int | None = None,
        browser: str | None = None,
    ) -> dict:
        """Activate a tab by explicit index or by query, then verify it."""
        debug_live(
            "tool_call",
            tool="browse_activate_tab",
            browser=browser,
            index=index,
            query_length=len(query) if isinstance(query, str) else None,
        )
        async with self.browser_lock:
            result = await asyncio.to_thread(
                self.browser.activate_tab,
                query,
                index,
                browser,
            )
        self._debug_browser_result("browse_activate_tab", result)
        return result.to_livekit_dict()

    @function_tool(
        name="capture_screen",
        description=(
            "Prend une capture d'ecran complete et l'enregistre dans un "
            "fichier PNG, puis relit le fichier pour confirmer "
            "l'enregistrement. Utilise ce tool quand l'utilisateur demande "
            "une capture d'ecran. path=None genere un nom horodate dans le "
            "dossier des captures ; display cible un ecran precis (1 par "
            "defaut). state_confirmed=true seulement si le fichier existe et "
            "n'est pas vide. Le resultat ne contient pas l'image, seulement "
            "son chemin et sa taille."
        ),
    )
    @self._journaled("capture_screen")
    @self._desktop_access
    async def capture_screen(
        path: str | None = None,
        display: int | None = None,
    ) -> dict:
        """Capture the full screen to a PNG file and verify it."""
        debug_live("tool_call", tool="capture_screen", display=display)
        async with self.screenshot_lock:
            result = await asyncio.to_thread(
                self.screenshot.capture_screen,
                path,
                display,
            )
        self._debug_screenshot_result("capture_screen", result)
        return result.to_livekit_dict()

    @function_tool(
        name="capture_region",
        description=(
            "Prend une capture d'une region rectangulaire de l'ecran "
            "(x, y, largeur, hauteur en points, origine en haut a gauche) et "
            "l'enregistre en PNG, puis verifie le fichier. N'invente jamais "
            "de coordonnees : utilise ce tool uniquement avec une region "
            "fournie par l'utilisateur ou par un tool fiable. state_confirmed "
            "=true seulement si le fichier a bien ete ecrit."
        ),
    )
    @self._journaled("capture_region")
    @self._desktop_access
    async def capture_region(
        x: int,
        y: int,
        width: int,
        height: int,
        path: str | None = None,
    ) -> dict:
        """Capture a rectangular region to a PNG file and verify it."""
        debug_live(
            "tool_call",
            tool="capture_region",
            width=width,
            height=height,
        )
        async with self.screenshot_lock:
            result = await asyncio.to_thread(
                self.screenshot.capture_region,
                x,
                y,
                width,
                height,
                path,
            )
        self._debug_screenshot_result("capture_region", result)
        return result.to_livekit_dict()

    @function_tool(
        name="capture_window",
        description=(
            "Prend une capture de la fenetre active, ou de la fenetre d'une "
            "application nommee (elle est d'abord mise au premier plan et "
            "verifiee), puis enregistre un PNG et relit le fichier. Utilise ce "
            "tool pour capturer une fenetre precise. Si la fenetre active ne "
            "correspond pas a l'application demandee, la capture est arretee "
            "(active_window_mismatch)."
        ),
    )
    @self._journaled("capture_window", "app_name")
    @self._desktop_access
    async def capture_window(
        app_name: str | None = None,
        path: str | None = None,
    ) -> dict:
        """Capture the active or a named window to a PNG file and verify it."""
        debug_live("tool_call", tool="capture_window", app_name=app_name)
        async with self.screenshot_lock:
            result = await asyncio.to_thread(
                self.screenshot.capture_window,
                app_name,
                path,
            )
        self._debug_screenshot_result("capture_window", result)
        return result.to_livekit_dict()

    @function_tool(
        name="describe_screen",
        description=(
            "Regarde l'ecran et decrit ce qui est visible. Capture (fenetre "
            "active par defaut, ou tout l'ecran avec target='screen') puis "
            "analyse l'image avec un modele multimodal, et renvoie une "
            "description. Utilise ce tool pour une demande comme qu'est-ce "
            "qu'il y a sur mon ecran. Rapporte seulement ce que l'analyse "
            "renvoie ; n'invente rien. Ce tool observe uniquement : il ne "
            "fournit aucune coordonnee et ne declenche aucune action. Pour "
            "cliquer ou taper, utilise Accessibility, jamais ce tool."
        ),
    )
    @self._journaled('describe_screen')
    @self._desktop_access
    async def describe_screen(
        target: str = "window",
        app_name: str | None = None,
    ) -> dict:
        """Capture then describe what is visible (read-only)."""
        guard = self._vision_guard("describe_screen")
        if guard is not None:
            return guard
        debug_live("tool_call", tool="describe_screen", source=target)
        async with self.vision_lock:
            result = await asyncio.to_thread(
                self.vision.describe_screen,
                target,
                app_name,
            )
        self._debug_vision_result("describe_screen", result)
        return result.to_livekit_dict()

    @function_tool(
        name="describe_camera",
        description=(
            "Regarde a travers la camera du Mac et decrit ce qui est visible : "
            "'qu'est-ce que tu vois', 'regarde ce que je tiens', 'decris la "
            "piece'. question : optionnelle, ce que l'utilisateur veut savoir "
            "sur la scene. Prend UNE seule photo au moment de l'appel, l'analyse "
            "puis la supprime ; aucun flux, rien n'est garde. Decrit les "
            "personnes sans jamais les identifier. N'appelle ce tool que sur "
            "demande explicite de regarder par la camera, jamais pour l'ecran."
        ),
    )
    @self._journaled('describe_camera')
    async def describe_camera(question: str | None = None) -> dict:
        """Take one camera still, describe it, delete it (read-only)."""
        guard = self._vision_guard("describe_camera")
        if guard is not None:
            return guard
        debug_live("tool_call", tool="describe_camera",
                   question_length=len(question) if isinstance(question, str) else None)
        async with self.vision_lock:
            result = await asyncio.to_thread(self.camera.describe, question)
        self._debug_tool_result("describe_camera", result)
        return result.to_livekit_dict()

    @function_tool(
        name="ask_about_screen",
        description=(
            "Regarde l'ecran et repond a une question sur ce qui est affiche "
            "(par exemple quelle temperature / quel prix est affiche, que dit "
            "cette page). Capture (fenetre active par defaut, ou tout l'ecran "
            "avec target='screen') puis analyse l'image. Si l'information "
            "n'est pas visible ou lisible, dis-le, n'invente jamais une "
            "valeur. Ce tool observe uniquement : aucune coordonnee, aucune "
            "action. Pour agir, utilise Accessibility."
        ),
    )
    @self._journaled('ask_about_screen')
    @self._desktop_access
    async def ask_about_screen(
        question: str,
        target: str = "window",
        app_name: str | None = None,
    ) -> dict:
        """Capture then answer a question about the screen (read-only)."""
        guard = self._vision_guard("ask_about_screen")
        if guard is not None:
            return guard
        debug_live(
            "tool_call",
            tool="ask_about_screen",
            source=target,
            question_length=len(question) if isinstance(question, str) else None,
        )
        async with self.vision_lock:
            result = await asyncio.to_thread(
                self.vision.ask_about_screen,
                question,
                target,
                app_name,
            )
        self._debug_vision_result("ask_about_screen", result)
        return result.to_livekit_dict()

    @function_tool(
        name="read_whatsapp_conversation",
        description=(
            "Lit et resume la conversation WhatsApp actuellement OUVERTE en la "
            "regardant (vision). Opt-in : utilise ce tool uniquement quand "
            "l'utilisateur demande explicitement de lire/resumer ses messages "
            "WhatsApp ('lis ma conversation', 'qu'est-ce qu'on m'a ecrit sur "
            "WhatsApp', 'resume cette discussion'). Il met WhatsApp au premier "
            "plan puis analyse l'ecran ; rapporte seulement ce qui est lu, sans "
            "inventer. Pour repondre ensuite, utilise prepare_send_message (envoi "
            "confirme). question : une question precise optionnelle sur la "
            "conversation."
        ),
    )
    @self._journaled("read_whatsapp_conversation")
    @self._desktop_access
    async def read_whatsapp_conversation(question: str | None = None) -> dict:
        """Read the open WhatsApp conversation via vision (opt-in)."""
        guard = self._vision_guard("read_whatsapp_conversation")
        if guard is not None:
            return guard
        debug_live("tool_call", tool="read_whatsapp_conversation")
        await asyncio.to_thread(self.windows.focus_window, "WhatsApp")
        await asyncio.sleep(self.messaging.search_settle_seconds)
        prompt = question.strip() if isinstance(question, str) and question.strip() else (
            "Resume la conversation WhatsApp ouverte : indique avec qui, et les "
            "derniers messages echanges. Rapporte seulement ce qui est lisible."
        )
        async with self.vision_lock:
            result = await asyncio.to_thread(
                self.vision.ask_about_screen, prompt, "window", "WhatsApp",
            )
        self._debug_vision_result("read_whatsapp_conversation", result)
        return result.to_livekit_dict()

    @function_tool(
        name="search_the_web",
        description=(
            "Cherche une information a jour sur le web et la synthetise a voix "
            "haute : actualites, meteo, prix, cours, resultats, 'qui est', 'quelles "
            "sont les nouvelles', 'quoi de neuf sur X'. La recherche tourne en "
            "arriere-plan (quelques secondes) ; des que tu appelles ce tool, dis a "
            "l'utilisateur que tu regardes, puis le resultat sera annonce tout seul. "
            "Si l'utilisateur ne precise pas de domaine pour 'les nouvelles', ne "
            "bloque pas : prends les grands titres a la une et propose d'affiner. "
            "N'utilise pas ce tool pour agir sur le Mac ni pour une question dont la "
            "reponse ne depend pas d'une information actuelle. question : la question "
            "complete en francais."
        ),
    )
    @self._journaled("search_the_web")
    async def search_the_web(question: str) -> dict:
        """Start a background web search; its result is announced by voice."""
        debug_live(
            "tool_call",
            tool="search_the_web",
            question_length=len(question) if isinstance(question, str) else None,
        )
        if not isinstance(question, str) or not question.strip():
            return ToolResult.failure(
                action="search_the_web",
                message="La question de recherche est vide.",
                error_code="invalid_question",
            ).to_livekit_dict()
        if self._web_running():
            return ToolResult.failure(
                action="search_the_web",
                message="Une recherche web est déjà en cours ; attends son résultat.",
                error_code="web_search_running",
            ).to_livekit_dict()
        self._web_task = asyncio.get_running_loop().create_task(
            self._run_web_search(question.strip())
        )
        return ToolResult.success(
            action="search_the_web",
            message=(
                "Recherche lancée. Dis simplement à l'utilisateur que tu regardes ; "
                "le résultat sera annonce dans un instant."
            ),
            search_started=True,
        ).to_livekit_dict()

    @function_tool(
        name="summarize_url",
        description=(
            "Lit une page web dont l'utilisateur donne l'adresse et la resume ou "
            "repond a une question a son sujet : 'resume cette page', 'que dit "
            "cet article sur ...'. url : l'adresse http/https ; question : une "
            "demande precise optionnelle. N'utilise que des URL fournies par "
            "l'utilisateur."
        ),
    )
    @self._journaled("summarize_url")
    async def summarize_url(url: str, question: str | None = None) -> dict:
        """Fetch a user-provided URL and summarize/answer from its content."""
        debug_live("tool_call", tool="summarize_url")
        result = await asyncio.to_thread(self.webread.summarize_url, url, question)
        self._debug_tool_result("summarize_url", result)
        return result.to_livekit_dict()

    @function_tool(
        name="morning_briefing",
        description=(
            "Prepare un point du jour parle : la date, un apercu de l'agenda et "
            "les principales actualites. Pour 'fais-moi le point', 'briefing du "
            "matin', 'quoi de neuf aujourd'hui'. Tourne en arriere-plan : des que "
            "tu l'appelles, dis que tu prepares le point ; le resultat sera "
            "annonce tout seul. topic : theme d'actualite optionnel."
        ),
    )
    @self._journaled("morning_briefing")
    async def morning_briefing(topic: str | None = None) -> dict:
        """Start a background briefing (date + agenda + news), announced by voice."""
        debug_live("tool_call", tool="morning_briefing")
        if self._briefing_running():
            return ToolResult.failure(
                action="morning_briefing",
                message="Un briefing est déjà en cours de préparation.",
                error_code="briefing_running",
            ).to_livekit_dict()
        self._briefing_task = asyncio.get_running_loop().create_task(
            self._run_briefing(topic)
        )
        return ToolResult.success(
            action="morning_briefing",
            message=(
                "Briefing en préparation. Dis à l'utilisateur que tu prepares le "
                "point du jour ; le résultat sera annonce dans un instant."
            ),
            briefing_started=True,
        ).to_livekit_dict()

    @function_tool(
        name="web_answer",
        description=(
            "Recherche une information a jour sur le web et renvoie une reponse "
            "synthetisee avec ses sources. Outil reserve aux taches longues : il "
            "BLOQUE le temps de la recherche (quelques secondes). Appuie-toi "
            "uniquement sur sa reponse et ses sources, n'invente rien. question : "
            "la question complete en francais."
        ),
    )
    @self._journaled("web_answer")
    async def web_answer(question: str) -> dict:
        """Blocking web search for the planner (not exposed to the voice model)."""
        debug_live(
            "tool_call",
            tool="web_answer",
            question_length=len(question) if isinstance(question, str) else None,
        )
        result = await asyncio.to_thread(self.knowledge.answer, question)
        return result.to_livekit_dict()

    return {
        "browse_open_url": browse_open_url,
        "browse_search_web": browse_search_web,
        "browse_get_active_tab": browse_get_active_tab,
        "browse_list_tabs": browse_list_tabs,
        "browse_activate_tab": browse_activate_tab,
        "capture_screen": capture_screen,
        "capture_region": capture_region,
        "capture_window": capture_window,
        "describe_screen": describe_screen,
        "describe_camera": describe_camera,
        "ask_about_screen": ask_about_screen,
        "read_whatsapp_conversation": read_whatsapp_conversation,
        "search_the_web": search_the_web,
        "summarize_url": summarize_url,
        "morning_briefing": morning_briefing,
        "web_answer": web_answer,
    }
