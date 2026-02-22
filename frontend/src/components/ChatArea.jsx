import React from 'react'
import MessageBubble from './MessageBubble'

export default function ChatArea({ messages, loading, chatEndRef, dark }) {
  const formatTime = (d) => {
    if (!d) return ''
    const h = d.getHours()
    const m = d.getMinutes().toString().padStart(2, '0')
    const ampm = h >= 12 ? 'م' : 'ص'
    const h12 = h % 12 || 12
    return `${h12}:${m} ${ampm}`
  }

  return (
    <main
      style={{
        flex: 1,
        overflowY: 'auto',
        padding: '24px 16px 120px',
        display: 'flex',
        flexDirection: 'column',
        gap: 20,
      }}
    >
      {/* Today badge */}
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <span
          style={{
            fontSize: 12,
            fontWeight: 500,
            color: '#8A94A0',
            background: dark ? '#262626' : '#e8e8ea',
            padding: '4px 14px',
            borderRadius: 999,
          }}
        >
          اليوم
        </span>
      </div>

      {messages.map((msg, i) => (
        <MessageBubble key={i} msg={msg} dark={dark} time={formatTime(msg.time)} />
      ))}

      {loading && (
        <div className="message-anim" style={{ display: 'flex', alignItems: 'flex-end', gap: 8 }}>
          <div
            style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              background: dark ? '#2C2210' : '#FFF8ED',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1.5px solid #C9921A',
              flexShrink: 0,
            }}
          >
            <span className="material-icons-round" style={{ color: '#C9921A', fontSize: 18 }}>home</span>
          </div>
          <div
            style={{
              background: dark ? '#121212' : '#fff',
              border: `1px solid ${dark ? '#2a2a2a' : '#e5e5e5'}`,
              padding: '16px 24px',
              borderRadius: '16px 0 16px 16px',
              display: 'flex',
              gap: 6,
            }}
          >
            <span className="typing-dot" />
            <span className="typing-dot" />
            <span className="typing-dot" />
          </div>
        </div>
      )}

      <div ref={chatEndRef} />
    </main>
  )
}
