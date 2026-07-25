/**
 * Web Speech API (SpeechRecognition) 类型声明
 *
 * TypeScript 内置 DOM lib 不包含 SpeechRecognition —— 它是 Chrome/Edge 的
 * 前缀实现（webkitSpeechRecognition），尚未进入 W3C 标准 lib。
 * 此声明覆盖语音模块（useWakeWord / useSpeechRecognition / useVoiceCommand）
 * 所需的接口，消除 (window as any).SpeechRecognition 这类逃逸。
 *
 * 参考：https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition
 */

/** 单条识别候选（confidence + transcript） */
interface SpeechRecognitionAlternative {
  readonly transcript: string
  readonly confidence: number
}

/** 一次识别结果（可含多个候选，支持 isFinal） */
interface SpeechRecognitionResult {
  readonly isFinal: boolean
  readonly length: number
  item(index: number): SpeechRecognitionAlternative
  [index: number]: SpeechRecognitionAlternative
}

/** 识别结果列表 */
interface SpeechRecognitionResultList {
  readonly length: number
  item(index: number): SpeechRecognitionResult
  [index: number]: SpeechRecognitionResult
}

/** onresult 回调事件 */
interface SpeechRecognitionEvent extends Event {
  readonly resultIndex: number
  readonly results: SpeechRecognitionResultList
}

/** onerror 回调事件 */
interface SpeechRecognitionErrorEvent extends Event {
  readonly error: string
  readonly message: string
}

/** 语音识别主接口（Chrome/Edge 前缀实现） */
interface SpeechRecognition extends EventTarget {
  continuous: boolean
  grammars: unknown
  interimResults: boolean
  lang: string
  maxAlternatives: number
  serviceURI: string

  start(): void
  stop(): void
  abort(): void

  onaudiostart: ((this: SpeechRecognition, ev: Event) => void) | null
  onaudioend: ((this: SpeechRecognition, ev: Event) => void) | null
  onstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onend: ((this: SpeechRecognition, ev: Event) => void) | null
  onsoundstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onsoundend: ((this: SpeechRecognition, ev: Event) => void) | null
  onspeechstart: ((this: SpeechRecognition, ev: Event) => void) | null
  onspeechend: ((this: SpeechRecognition, ev: Event) => void) | null
  onnomatch: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null
  onresult: ((this: SpeechRecognition, ev: SpeechRecognitionEvent) => void) | null
  onerror: ((this: SpeechRecognition, ev: SpeechRecognitionErrorEvent) => void) | null
}

/** SpeechRecognition 构造器类型（替代 declare var 避免 no-redeclare） */
type SpeechRecognitionConstructor = new () => SpeechRecognition

/** 扩展 Window：标准名 + webkit 前缀名 */
interface Window {
  SpeechRecognition?: SpeechRecognitionConstructor
  webkitSpeechRecognition?: SpeechRecognitionConstructor
}
