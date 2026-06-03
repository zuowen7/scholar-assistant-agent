import { useVoiceRouter } from '../useVoiceRouter'
import { registerTier1Commands } from './tier1-navigation'
import { registerTier2Commands } from './tier2-file'
import { registerTier3Commands } from './tier3-editor'
import { registerTier4Commands } from './tier4-translation'
import { registerTier5Commands } from './tier5-mindmap'

export function registerAllVoiceCommands() {
  const router = useVoiceRouter()
  router.clearCommands()

  registerTier1Commands(router.registerCommands)
  registerTier2Commands(router.registerCommands)
  registerTier3Commands(router.registerCommands)
  registerTier4Commands(router.registerCommands)
  registerTier5Commands(router.registerCommands)
}
