import { useVoiceRouter } from '../useVoiceRouter'
import { registerTier1Commands } from './tier1-navigation'
import { registerTier2Commands } from './tier2-file'
import { registerTier3Commands } from './tier3-editor'

export function registerAllVoiceCommands() {
  const router = useVoiceRouter()
  router.clearCommands()

  registerTier1Commands(router.registerCommands)
  registerTier2Commands(router.registerCommands)
  registerTier3Commands(router.registerCommands)
}
