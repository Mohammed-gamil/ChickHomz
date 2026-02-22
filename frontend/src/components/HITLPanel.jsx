import React, { useState } from 'react'
import ProductCard from './ProductCard'

export default function HITLPanel({ data, dark, onApprove, onReject }) {
  const products = data?.products || []
  const confidence = data?.confidence_score || 0
  const matchedTypes = data?.matched_types || []
  const checklist = data?.checklist || []
  const preview = data?.response_preview || ''
  const summaryNote = data?.summary_note || ''

  // Interactive checklist state — start from LLM's passed/failed assessment
  const [checked, setChecked] = useState(() =>
    checklist.map((item) => (typeof item === 'object' ? item.passed : true))
  )

  const toggle = (i) => setChecked((prev) => prev.map((v, idx) => (idx === i ? !v : v)))

  const bg = dark ? '#1a1a1a' : '#fff'
  const border = dark ? '#333' : '#e0e0e0'
  const textColor = dark ? '#f1f1f1' : '#1a1a1a'
  const subText = dark ? '#aaa' : '#666'
  const rowHover = dark ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.02)'

  const confidencePct = Math.round(confidence * 100)
  const confidenceColor =
    confidencePct >= 80 ? '#4CAF50' : confidencePct >= 50 ? '#FF9800' : '#f44336'

  const failedCount = checked.filter((v) => !v).length

  const handleApprove = () => {
    const feedback = checklist.map((item, i) => ({
      label: typeof item === 'object' ? item.label : String(item),
      confirmed: checked[i],
    }))
    onApprove(feedback)
  }

  return (
    <div
      className="message-anim"
      style={{
        background: bg,
        border: `2px solid #C9921A`,
        borderRadius: 20,
        padding: 24,
        margin: '8px 0',
        maxWidth: '95%',
        alignSelf: 'flex-start',
        boxShadow: '0 8px 32px rgba(201,146,26,0.15)',
      }}
    >
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 16 }}>
        <span className="material-icons-round" style={{ color: '#C9921A', fontSize: 24 }}>
          verified_user
        </span>
        <div style={{ flex: 1 }}>
          <h3 style={{ fontSize: 16, fontWeight: 700, color: textColor, margin: 0 }}>
            مراجعة التوصيات قبل الإرسال
          </h3>
          <p style={{ fontSize: 12, color: subText, margin: 0 }}>
            راجع قائمة الفحص وعدّلها، ثم اعتمد أو ارفض
          </p>
        </div>
        {/* Confidence */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
          <div
            style={{
              width: 80,
              height: 6,
              background: dark ? '#333' : '#e0e0e0',
              borderRadius: 3,
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                width: `${confidencePct}%`,
                height: '100%',
                background: confidenceColor,
                borderRadius: 3,
              }}
            />
          </div>
          <span style={{ fontSize: 12, fontWeight: 700, color: confidenceColor, minWidth: 32 }}>
            {confidencePct}%
          </span>
        </div>
      </div>

      {/* Matched types */}
      {matchedTypes.length > 0 && (
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 14 }}>
          {matchedTypes.map((t, i) => (
            <span
              key={i}
              style={{
                fontSize: 11,
                background: 'rgba(201,146,26,0.15)',
                color: '#C9921A',
                padding: '2px 10px',
                borderRadius: 999,
                fontWeight: 600,
              }}
            >
              {t}
            </span>
          ))}
        </div>
      )}

      {/* Products */}
      {products.length > 0 && (
        <div style={{ marginBottom: 16 }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: subText, marginBottom: 8 }}>
            المنتجات المقترحة ({products.length})
          </p>
          <div style={{ display: 'flex', gap: 10, overflowX: 'auto', paddingBottom: 8 }}>
            {products.map((p, i) => (
              <ProductCard key={i} product={p} dark={dark} />
            ))}
          </div>
        </div>
      )}

      {/* Response preview */}
      {preview && (
        <div
          style={{
            background: dark ? '#222' : '#f9f9f9',
            border: `1px solid ${border}`,
            borderRadius: 12,
            padding: 14,
            marginBottom: 16,
          }}
        >
          <p style={{ fontSize: 12, fontWeight: 600, color: subText, marginBottom: 6 }}>
            معاينة الرد
          </p>
          <p style={{ fontSize: 13, lineHeight: 1.7, color: textColor, whiteSpace: 'pre-wrap' }}>
            {preview}
          </p>
        </div>
      )}

      {/* Interactive Checklist */}
      {checklist.length > 0 && (
        <div style={{ marginBottom: 18 }}>
          <p style={{ fontSize: 12, fontWeight: 600, color: subText, marginBottom: 8 }}>
            قائمة الفحص — اضغط على أي بند لتعديله
          </p>
          <div style={{ border: `1px solid ${border}`, borderRadius: 12, overflow: 'hidden' }}>
            {checklist.map((item, i) => {
              const isObj = typeof item === 'object' && item !== null
              const label = isObj ? item.label : String(item)
              const detail = isObj ? item.detail : ''
              const isChecked = checked[i]

              return (
                <div
                  key={i}
                  onClick={() => toggle(i)}
                  style={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    gap: 12,
                    padding: '10px 14px',
                    cursor: 'pointer',
                    borderBottom: i < checklist.length - 1 ? `1px solid ${border}` : 'none',
                    transition: 'background 0.15s',
                    userSelect: 'none',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = rowHover)}
                  onMouseLeave={(e) => (e.currentTarget.style.background = 'transparent')}
                >
                  {/* Custom checkbox */}
                  <div
                    style={{
                      width: 20,
                      height: 20,
                      borderRadius: 6,
                      border: `2px solid ${isChecked ? '#4CAF50' : '#f44336'}`,
                      background: isChecked ? 'rgba(76,175,80,0.12)' : 'rgba(244,67,54,0.08)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: 2,
                      transition: 'all 0.15s',
                    }}
                  >
                    <span
                      className="material-icons-round"
                      style={{ fontSize: 14, color: isChecked ? '#4CAF50' : '#f44336' }}
                    >
                      {isChecked ? 'check' : 'close'}
                    </span>
                  </div>

                  <div style={{ flex: 1, minWidth: 0 }}>
                    <span style={{ fontSize: 13, color: textColor, fontWeight: 500, lineHeight: 1.5 }}>
                      {label}
                    </span>
                    {detail && (
                      <p style={{ fontSize: 11, color: subText, margin: '2px 0 0', lineHeight: 1.4 }}>
                        {detail}
                      </p>
                    )}
                  </div>
                </div>
              )
            })}
          </div>

          {summaryNote && (
            <p style={{ fontSize: 12, color: '#C9921A', marginTop: 10, fontWeight: 600 }}>
              📝 {summaryNote}
            </p>
          )}

          {failedCount > 0 && (
            <div
              style={{
                marginTop: 10,
                padding: '8px 12px',
                borderRadius: 8,
                background: 'rgba(244,67,54,0.08)',
                border: '1px solid rgba(244,67,54,0.2)',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <span className="material-icons-round" style={{ color: '#f44336', fontSize: 16 }}>
                warning
              </span>
              <span style={{ fontSize: 12, color: '#f44336', fontWeight: 500 }}>
                {failedCount} {failedCount === 1 ? 'بند' : 'بنود'} لم تجتز الفحص
              </span>
            </div>
          )}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
        <button
          onClick={() => onReject('')}
          style={{
            padding: '10px 24px',
            borderRadius: 12,
            border: `1px solid ${dark ? '#555' : '#ccc'}`,
            background: 'transparent',
            color: textColor,
            fontSize: 14,
            fontWeight: 600,
            fontFamily: "'Tajawal', sans-serif",
            cursor: 'pointer',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = '#f44336'
            e.currentTarget.style.color = '#f44336'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = dark ? '#555' : '#ccc'
            e.currentTarget.style.color = textColor
          }}
        >
          <span className="material-icons-round" style={{ fontSize: 16, verticalAlign: 'middle', marginLeft: 4 }}>
            close
          </span>
          رفض وإيقاف
        </button>
        <button
          onClick={handleApprove}
          style={{
            padding: '10px 28px',
            borderRadius: 12,
            border: 'none',
            background: '#C9921A',
            color: '#fff',
            fontSize: 14,
            fontWeight: 700,
            fontFamily: "'Tajawal', sans-serif",
            cursor: 'pointer',
            boxShadow: '0 4px 16px rgba(201,146,26,0.3)',
            transition: 'all 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.filter = 'brightness(1.15)')}
          onMouseLeave={(e) => (e.currentTarget.style.filter = 'brightness(1)')}
        >
          <span className="material-icons-round" style={{ fontSize: 16, verticalAlign: 'middle', marginLeft: 4 }}>
            check
          </span>
          اعتماد وإرسال
        </button>
      </div>
    </div>
  )
}
