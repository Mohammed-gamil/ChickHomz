import React from 'react'
import ProductCard from './ProductCard'

export default function MessageBubble({ msg, dark, time }) {
  const isUser = msg.role === 'user'

  if (isUser) {
    return (
      <div className="message-anim" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 4 }}>
        <div
          style={{
            background: dark ? '#2C2C2C' : '#1E1E1E',
            color: '#fff',
            padding: '14px 18px',
            borderRadius: '16px 16px 0 16px',
            maxWidth: '85%',
            boxShadow: '0 2px 8px rgba(0,0,0,0.15)',
            position: 'relative',
            overflow: 'hidden',
          }}
        >
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, rgba(255,255,255,0.05), transparent)', pointerEvents: 'none' }} />
          <p style={{ fontSize: 14, lineHeight: 1.7, position: 'relative', zIndex: 1 }}>{msg.text}</p>
        </div>
        {time && <span style={{ fontSize: 10, color: '#8A94A0', padding: '0 4px' }}>{time}</span>}
      </div>
    )
  }

  // AI message
  return (
    <div className="message-anim" style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 4 }}>
      <div style={{ display: 'flex', alignItems: 'flex-end', gap: 8, maxWidth: '92%', width: '100%' }}>
        {/* Avatar */}
        <div
          style={{
            width: 32,
            height: 32,
            borderRadius: '50%',
            background: dark ? '#2C2210' : '#FFF8ED',
            flexShrink: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '1.5px solid #C9921A',
            marginBottom: msg.products?.length > 0 ? 24 : 0,
          }}
        >
          <span className="material-icons-round" style={{ color: '#C9921A', fontSize: 18 }}>home</span>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
          {/* Text bubble */}
          <div
            style={{
              background: dark ? '#121212' : '#fff',
              border: `1px solid ${dark ? '#2a2a2a' : '#e5e5e5'}`,
              padding: '14px 18px',
              borderRadius: '16px 0 16px 16px',
              boxShadow: '0 1px 4px rgba(0,0,0,0.05)',
              width: 'fit-content',
            }}
          >
            <p style={{ fontSize: 14, lineHeight: 1.7, whiteSpace: 'pre-wrap' }}>{msg.text}</p>
            {msg.streaming && (
              <div style={{ display: 'flex', gap: 4, marginTop: 8, alignItems: 'center' }}>
                <span className="typing-dot" style={{ width: 6, height: 6 }} />
                <span className="typing-dot" style={{ width: 6, height: 6 }} />
                <span className="typing-dot" style={{ width: 6, height: 6 }} />
              </div>
            )}
          </div>

          {/* Product cards */}
          {msg.products?.length > 0 && (
            <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 4 }}>
              {msg.products.map((p, i) => (
                <ProductCard key={i} product={p} dark={dark} />
              ))}
            </div>
          )}

          {time && (
            <span style={{ fontSize: 10, color: '#8A94A0', padding: '0 4px', alignSelf: 'flex-start' }}>
              {time}
            </span>
          )}
        </div>
      </div>
    </div>
  )
}
