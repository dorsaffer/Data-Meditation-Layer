'use client'

import { ReactNode, useState } from 'react'

export interface AnalyticsTab {
  key: string
  title: string
  description: string
  content: ReactNode
}

export function AnalyticsTabs({ tabs }: { tabs: AnalyticsTab[] }) {
  const [activeKey, setActiveKey] = useState(tabs[0]?.key)
  const active = tabs.find((tab) => tab.key === activeKey) ?? tabs[0]

  return (
    <div>
      <div role="tablist" aria-label="Analytics views" className="flex flex-wrap gap-1 border-b border-slate-200">
        {tabs.map((tab) => {
          const isActive = tab.key === active?.key
          return (
            <button
              key={tab.key}
              type="button"
              role="tab"
              id={`analytics-tab-${tab.key}`}
              aria-selected={isActive}
              aria-controls={`analytics-panel-${tab.key}`}
              onClick={() => setActiveKey(tab.key)}
              className={`-mb-px rounded-t-md border border-b-0 px-4 py-2 text-sm font-medium transition-colors ${
                isActive
                  ? 'border-slate-200 bg-white text-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab.title}
            </button>
          )
        })}
      </div>

      {active && (
        <section
          role="tabpanel"
          id={`analytics-panel-${active.key}`}
          aria-labelledby={`analytics-tab-${active.key}`}
          className="rounded-b-lg rounded-tr-lg border border-slate-200 bg-white p-6"
        >
          <p className="text-sm text-slate-500">{active.description}</p>
          <div className="mt-4">{active.content}</div>
        </section>
      )}
    </div>
  )
}
