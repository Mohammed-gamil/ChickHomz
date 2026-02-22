import React, { useState } from 'react'

export default function InputBar({ onSend, loading, dark }) {
  const [text, setText] = useState('')

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!text.trim()) return
    onSend(text.trim())
    setText('')
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  const bg = dark ? 'rgba(18,18,18,0.95)' : 'rgba(245,245,247,0.95)'
  const border = dark ? '#2a2a2a' : '#e5e5e5'
  const inputBg = dark ? '#1E1E1E' : '#fff'

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        background: bg,
        backdropFilter: 'blur(16px)',
        WebkitBackdropFilter: 'blur(16px)',
        borderTop: `1px solid ${border}`,
        padding: '12px 16px 28px',
        zIndex: 30,
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          maxWidth: 800,
          margin: '0 auto',
        }}
      >
        <div style={{ flex: 1, position: 'relative' }}>
          <input
            type="text"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="اكتبي ما تبحثين عنه... مثلاً: أنا بفرش غرفة نوم بميزانية ٥٠٠٠ ج.م"
            disabled={loading}
            style={{
              width: '100%',
              background: inputBg,
              border: 'none',
              color: dark ? '#fff' : '#1a1a1a',
              borderRadius: 999,
              padding: '14px 48px 14px 18px',
              fontSize: 14,
              fontFamily: "'Tajawal', sans-serif",
              outline: 'none',
              boxShadow: 'inset 0 1px 3px rgba(0,0,0,0.06)',
            }}
            onFocus={(e) =>
              (e.target.style.boxShadow =
                '0 0 0 2px rgba(201,146,26,0.35), inset 0 1px 3px rgba(0,0,0,0.06)')
            }
            onBlur={(e) => (e.target.style.boxShadow = 'inset 0 1px 3px rgba(0,0,0,0.06)')}
          />
        </div>

        <button
          type="submit"
          disabled={loading || !text.trim()}
          style={{
            width: 48,
            height: 48,
            borderRadius: '50%',
            background: '#C9921A',
            border: 'none',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            cursor: loading || !text.trim() ? 'not-allowed' : 'pointer',
            boxShadow: '0 0 15px rgba(201,146,26,0.25)',
            transition: 'transform 0.2s, opacity 0.2s',
            opacity: loading || !text.trim() ? 0.5 : 1,
            flexShrink: 0,
          }}
          onMouseEnter={(e) => {
            if (!loading && text.trim()) e.currentTarget.style.transform = 'scale(1.05)'
          }}
          onMouseLeave={(e) => (e.currentTarget.style.transform = 'scale(1)')}
        >
          <span className="material-icons-round" style={{ color: '#fff', fontSize: 24 }}>send</span>
        </button>
      </form>
    </div>
  )
}
