/**
 * 句对齐工具 — 模仿 DeepL 的悬停高亮体验
 *
 * 核心思路：
 * - 把段落切分为句子，记录每个句子的字符位置
 * - hover 原文中某句时，按句序区间映射到译文（支持一对多）
 * - 不改翻译逻辑，纯前端视觉层对齐
 *
 * 切分逻辑与后端 `python/src/chunker/splitter.py::_split_sentences` 保持一致，
 * 保护学术缩写（et al. / Fig. / e.g. / i.e. / vs. 等）和小数（3.14）不被误切。
 */

export interface Sentence {
  text: string
  start: number
  end: number
}

// 学术常见缩写——这些缩写后的句号不代表句子结束。
// 与后端 splitter.py::_ACADEMIC_ABBREVS 保持一致。
const ACADEMIC_ABBREVS = [
  'et al',
  'etc',
  'fig',
  'figs',
  'eq',
  'eqs',
  'ref',
  'refs',
  'vol',
  'no',
  'pp',
  'cf',
  'e.g',
  'i.e',
  'vs',
  'ed',
  'eds',
  'rev',
  'proc',
  'inst',
  'dept',
  'univ',
  'sci',
  'tech',
  'phys',
  'chem',
  'biol',
  'med',
  'hum',
  'evol',
  'anthrop',
  'soc',
  'pol',
  'econ',
  'psych',
  'nat',
  'int',
  'inc',
  'ltd',
  'co',
  'st',
  'dr',
  'mr',
  'mrs',
  'prof',
  'sr',
  'jr',
  'ph',
  'dc',
  'ba',
  'ma',
  'approx',
  'max',
  'min',
  'avg',
  'std',
  'var',
  'def',
  'thm',
  'lem',
  'cor',
  'prop',
]

const escapeRegExp = (value: string) => value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
// 预编译缩写正则（\b 边界 + 缩写 + 句点 + 空白）
const ABBREV_RE = new RegExp(
  '\\b(?:' + ACADEMIC_ABBREVS.map(escapeRegExp).join('|') + ')\\.\\s',
  'gi',
)
// 小数正则：数字.数字
const DECIMAL_RE = /(\d)\.(\d)/g
// 用单字符私有区码位保护非句末句点。替换前后长度一致，因此 match.index
// 始终仍是原文坐标，可安全用于双语 hover 对齐。
const PROTECTED_DOT = '\uE000'

/**
 * 切分句子（英文/中文）
 *
 * 英文采用与后端一致的缩写/小数保护策略：
 * 1. 用等长保护字符替换 "et al. " / "Fig. " / "e.g. " / "3.14" 中的句点
 * 2. 按句末标点（.!?）+ 可选闭合引号切分
 * 3. 还原受保护的句点
 * 4. 保留没有句末标点的尾句和原始字符坐标
 */
export function splitSentences(text: string, lang: 'en' | 'zh'): Sentence[] {
  const out: Sentence[] = []

  const pushRange = (start: number, end: number) => {
    const raw = text.slice(start, end)
    const leading = raw.search(/\S/)
    if (leading < 0) return
    const trailing = raw.length - raw.trimEnd().length
    const actualStart = start + leading
    const actualEnd = end - trailing
    out.push({ text: text.slice(actualStart, actualEnd), start: actualStart, end: actualEnd })
  }

  if (lang === 'en') {
    // 1. 保护缩写 + 小数，仅替换句点以保持原文字符位置不变
    let protectedText = text
    ABBREV_RE.lastIndex = 0
    protectedText = protectedText.replace(ABBREV_RE, (m) => m.replaceAll('.', PROTECTED_DOT))
    protectedText = protectedText.replace(DECIMAL_RE, `$1${PROTECTED_DOT}$2`)

    // 2. 只在真正的句末标点处切分，并保留最后一个无标点尾句。
    // 英文句点后必须是空白或文本结束，避免把文件名/URL 拆开。
    let rangeStart = 0
    for (let i = 0; i < protectedText.length; i++) {
      if (!'.!?'.includes(protectedText[i])) continue
      let end = i + 1
      while (end < protectedText.length && '.!?'.includes(protectedText[end])) end++
      while (end < protectedText.length && /["')\]]/.test(protectedText[end])) end++
      if (end < protectedText.length && !/\s/.test(protectedText[end])) continue
      pushRange(rangeStart, end)
      rangeStart = end
      i = end - 1
    }
    pushRange(rangeStart, text.length)

    if (out.length === 0) out.push({ text: text.trim(), start: 0, end: text.length })
    return out
  } else {
    // 中文分号连接同一句中的并列分句，不应当作句末。
    let rangeStart = 0
    for (let i = 0; i < text.length; i++) {
      if (!'。！？'.includes(text[i])) continue
      let end = i + 1
      while (end < text.length && '。！？'.includes(text[end])) end++
      while (end < text.length && /[”’」』】）]/.test(text[end])) end++
      pushRange(rangeStart, end)
      rangeStart = end
      i = end - 1
    }
    pushRange(rangeStart, text.length)

    // 兜底：如果没切出任何句子，整个文本作为一个句子
    if (out.length === 0) {
      out.push({ text, start: 0, end: text.length })
    }

    return out
  }
}

/**
 * 查找对应的译文句子索引
 *
 * @param origSentences 原文句子列表
 * @param origLen 原文总长度
 * @param transSentences 译文句子列表
 * @param transLen 译文总长度
 * @param hoveredOrigIdx 当前 hover 的原文句子索引
 * @returns 对应的译文句子索引
 */
export function findCorrespondingSentenceIdx(
  origSentences: Sentence[],
  origLen: number,
  transSentences: Sentence[],
  transLen: number,
  hoveredOrigIdx: number,
): number {
  if (hoveredOrigIdx < 0 || hoveredOrigIdx >= origSentences.length) return -1
  void origLen
  void transLen
  const indices = findCorrespondingSentenceIndices(origSentences, transSentences, hoveredOrigIdx)
  if (indices.length === 0) return -1
  const sourceMid = (hoveredOrigIdx + 0.5) / origSentences.length
  return indices.reduce((best, current) => {
    const bestDistance = Math.abs((best + 0.5) / transSentences.length - sourceMid)
    const currentDistance = Math.abs((current + 0.5) / transSentences.length - sourceMid)
    return currentDistance < bestDistance ? current : best
  })
}

/** Map one source sentence to every target sentence whose ordinal interval
 * overlaps it. This keeps one-to-many translations visibly grouped. */
export function findCorrespondingSentenceIndices(
  sourceSentences: Sentence[],
  targetSentences: Sentence[],
  sourceIndex: number,
): number[] {
  if (sourceIndex < 0 || sourceIndex >= sourceSentences.length || targetSentences.length === 0)
    return []
  if (sourceSentences.length === targetSentences.length) return [sourceIndex]
  const sourceStart = sourceIndex / sourceSentences.length
  const sourceEnd = (sourceIndex + 1) / sourceSentences.length
  const matches: number[] = []
  for (let index = 0; index < targetSentences.length; index++) {
    const targetStart = index / targetSentences.length
    const targetEnd = (index + 1) / targetSentences.length
    if (Math.min(sourceEnd, targetEnd) - Math.max(sourceStart, targetStart) > 1e-9)
      matches.push(index)
  }
  return matches
}

/**
 * 渲染带句子标记的HTML
 *
 * @param text 原文/译文
 * @param lang 语言
 * @param blockId 块ID
 * @param side 'orig' | 'trans'
 * @returns 带标记的HTML字符串
 */
export function renderSentenceMarkedHtml(
  text: string,
  lang: 'en' | 'zh',
  blockId: string,
  side: 'orig' | 'trans',
): string {
  const sentences = splitSentences(text, lang)

  if (sentences.length <= 1) {
    // 只有一句，不需要标记
    return escapeHtml(text)
  }

  let cursor = 0
  let html = ''
  sentences.forEach((sent, idx) => {
    html += escapeHtml(text.slice(cursor, sent.start))
    html += `<span data-sent-idx="${idx}" data-block-id="${escapeHtml(blockId)}" data-side="${side}" class="sent">${escapeHtml(text.slice(sent.start, sent.end))}</span>`
    cursor = sent.end
  })
  return html + escapeHtml(text.slice(cursor))
}

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
