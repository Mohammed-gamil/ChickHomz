import React from 'react'

/**
 * Lightweight inline markdown renderer (split-based, no stateful regex).
 * Handles: **bold**, ~~strikethrough~~, [text](url), * /- bullet lists, empty lines.
 */

// Splits text into plain-text and markdown-token alternating segments
function renderInline(text) {
  // split() with a capturing group preserves the delimiters in the result array
  const tokens = text.split(/(\*\*[^*\n]+\*\*|~~[^~\n]+~~|\[[^\]\n]+\]\([^)\n]+\))/)
  return tokens.map((t, i) => {
    if (t.startsWith('**') && t.endsWith('**') && t.length > 4) {
      return (
        <strong key={i} style={{ fontWeight: 700 }}>
          {t.slice(2, -2)}
        </strong>
      )
    }
    if (t.startsWith('~~') && t.endsWith('~~') && t.length > 4) {
      return (
        <span key={i} style={{ textDecoration: 'line-through', color: '#999', fontSize: '0.9em' }}>
          {t.slice(2, -2)}
        </span>
      )
    }
    const linkMatch = t.match(/^\[([^\]]+)\]\(([^)]+)\)$/)
    if (linkMatch) {
      return (
        <a
          key={i}
          href={linkMatch[2]}
          target="_blank"
          rel="noopener noreferrer"
          style={{ color: '#C9921A', textDecoration: 'underline', fontWeight: 500 }}
        >
          {linkMatch[1]}
        </a>
      )
    }
    return t || null
  })
}

export default function MarkdownText({ text, dark, style }) {
  if (!text) return null

  // Normalise Windows line endings
  const lines = text.replace(/\r\n/g, '\n').replace(/\r/g, '\n').split('\n')

  const elements = []
  let listItems = []
  let listKey = 0

  const flushList = () => {
    if (listItems.length === 0) return
    elements.push(
      <ul
        key={`ul-${listKey++}`}
        style={{
          margin: '6px 0',
          paddingInlineStart: 20,
          listStyleType: 'disc',
        }}
      >
        {listItems}
      </ul>
    )
    listItems = []
  }

  lines.forEach((rawLine, i) => {
    const line = rawLine.trimEnd()
    // Match any indentation level: "* text", "  * text", "- text", "  - text"
    const bulletMatch = line.match(/^\s*[\*\-]\s+(.+)/)
    if (bulletMatch) {
      listItems.push(
        <li key={i} style={{ marginBottom: 4, lineHeight: 1.7 }}>
          {renderInline(bulletMatch[1])}
        </li>
      )
    } else {
      flushList()
      if (line.trim() === '') {
        if (elements.length > 0) {
          elements.push(<div key={`gap-${i}`} style={{ height: 6 }} />)
        }
      } else {
        elements.push(
          <p key={i} style={{ margin: 0, lineHeight: 1.7 }}>
            {renderInline(line)}
          </p>
        )
      }
    }
  })

  flushList()

  return (
    <div
      dir="auto"
      style={{
        fontSize: 14,
        color: dark ? '#e5e5e5' : '#1a1a1a',
        ...style,
      }}
    >
      {elements}
    </div>
  )
}
