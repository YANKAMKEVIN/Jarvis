"""Desktop-only voice settings; acknowledged by Qt before reporting success."""
import asyncio
from concurrent.futures import Future
from livekit.agents import function_tool


def presentation_tools(registry):
    @function_tool(name='configure_companion', description=(
        'Change les preferences du compagnon sur demande explicite: appearance=id du personnage ou choose pour ouvrir le selecteur, voice=nom Gemini ou choose pour ouvrir les voix, '
        'tone=balanced/warm/playful, detail=short/normal/detailed, quiet=true pour les reponses ecrites. '
        'Les voix changent a la prochaine connexion. Champs vides conserves. Ne declare le changement que si ok=true.'))
    async def configure_companion(appearance:str='', voice:str='', tone:str='', detail:str='', quiet:bool|None=None)->dict:
        observer=getattr(registry,'presentation_observer',None)
        if observer is None:return {'ok':False,'message':'Compagnon desktop indisponible.'}
        receipt=Future()
        observer({'type':'companion_config','appearance':appearance,'voice':voice,'tone':tone,
                  'detail':detail,'quiet':quiet,'receipt':receipt})
        try:return await asyncio.wait_for(asyncio.wrap_future(receipt),3)
        except asyncio.TimeoutError:return {'ok':False,'message':'Réglage non confirmé. Réessayez depuis les réglages.'}
    return [configure_companion]
