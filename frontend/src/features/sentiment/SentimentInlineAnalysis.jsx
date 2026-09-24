import { Bot, CircleGauge, MessageCircle, RefreshCw, Target, TrendingUp } from 'lucide-react'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { Metric, Pill, SectionHeader } from '../../components/common/UI'
import { fmt } from '../../lib/metrics'

export default function SentimentInlineAnalysis({ analysis, loading, error, onReanalyze }) {
  if (loading) {
    return (
      <div className="sentiment-inline-analysis loading-state">
        <div className="sentiment-analysis-loader"><div className="loader" /></div>
        <div>
          <div className="eyebrow">Post-level AI analysis</div>
          <h3>Reading audience voice…</h3>
          <p>Instagram comments are collected once, then Groq classifies the sample. The result is persisted so this work is not repeated on refresh.</p>
        </div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="sentiment-inline-analysis error-state">
        <div>
          <div className="eyebrow">Post-level AI analysis</div>
          <h3>Analysis failed</h3>
          <p>{error}</p>
        </div>
        <button className="ghost-btn" onClick={onReanalyze}><RefreshCw size={14} /> Try again</button>
      </div>
    )
  }

  if (!analysis) return null

  const summary = analysis.summary || {}
  const sample = analysis.sample || {}
  const results = Array.isArray(analysis.results) ? analysis.results : []
  const topics = Array.isArray(analysis.topics) ? analysis.topics : []
  const pie = [
    { name: 'Positive', value: Number(summary.positive || 0) },
    { name: 'Neutral', value: Number(summary.neutral || 0) },
    { name: 'Negative', value: Number(summary.negative || 0) },
  ]
  const maxTopic = Math.max(1, ...topics.map(item => Number(item.count || 0)))

  return (
    <div className="sentiment-inline-analysis">
      <div className="sentiment-inline-head">
        <div>
          <div className="eyebrow">AI analysis ready</div>
          <h3>Audience voice</h3>
          <p>{sample.selected || results.length} comments analyzed with {analysis.model || 'Groq'}.</p>
        </div>
        <div className="selected-post-actions">
          <Pill>{sample.selected || results.length} sampled</Pill>
          <Pill>{sample.hasLikeSignal ? `${sample.likedShare || 0}% liked signal` : 'Mixed random sample'}</Pill>
          {analysis.partial && <Pill tone="negative">Partial batch result</Pill>}
          <Pill tone="positive">Groq complete</Pill>
          <button className="ghost-btn" onClick={onReanalyze}><RefreshCw size={13} /> Re-analyze</button>
        </div>
      </div>

      <div className="metric-grid sentiment-inline-metrics">
        <Metric icon={MessageCircle} label="Sampled" value={fmt(sample.selected || results.length)} sub="Instagram comments" accent="violet" />
        <Metric icon={TrendingUp} label="Positive" value={`${Number(summary.positivePct || 0).toFixed(1)}%`} sub={`${summary.positive || 0} comments`} accent="mint" />
        <Metric icon={CircleGauge} label="Neutral" value={`${Number(summary.neutralPct || 0).toFixed(1)}%`} sub={`${summary.neutral || 0} comments`} accent="blue" />
        <Metric icon={Target} label="Negative" value={`${Number(summary.negativePct || 0).toFixed(1)}%`} sub={`${summary.negative || 0} comments`} accent="pink" />
        <Metric icon={Bot} label="Model" value="GPT-OSS" sub={analysis.model || 'Groq'} accent="orange" />
      </div>

      <div className="grid-two sentiment-inline-grid">
        <div className="panel nested-panel">
          <SectionHeader eyebrow="Tone mix" title="Audience sentiment" />
          <div className="chart"><ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" innerRadius={58} outerRadius={86} paddingAngle={3}>
                <Cell fill="#10b981" /><Cell fill="#94a3b8" /><Cell fill="#f43f5e" />
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer></div>
          <div className="sentiment-legend">
            <span><i className="mint" />{Number(summary.positivePct || 0).toFixed(1)}% positive</span>
            <span><i className="slate" />{Number(summary.neutralPct || 0).toFixed(1)}% neutral</span>
            <span><i className="rose" />{Number(summary.negativePct || 0).toFixed(1)}% negative</span>
          </div>
        </div>

        <div className="panel nested-panel">
          <SectionHeader eyebrow="Conversation themes" title="What people are talking about" />
          {topics.length ? (
            <div className="topic-list">
              {topics.map(topic => (
                <div className="topic-row" key={topic.topic}>
                  <span>{topic.topic}</span>
                  <div className="topic-track"><b style={{ width: `${Math.min(100, Number(topic.count || 0) / maxTopic * 100)}%` }} /></div>
                  <strong>{topic.count}</strong>
                </div>
              ))}
            </div>
          ) : <div className="muted">No topic results were returned.</div>}
          {analysis.errors?.length ? <div className="analysis-note">{analysis.errors[0]}</div> : null}
        </div>
      </div>

      <div className="panel nested-panel comments-panel">
        <SectionHeader eyebrow="Comment review" title="Sampled comments" copy={`Showing ${Math.min(20, results.length)} of ${results.length} analyzed comments.`} />
        <div className="comments">
          {results.slice(0, 20).map((result, index) => (
            <div className="comment-row" key={`${result.id || index}-${result.username || ''}`}>
              <div className="avatar">{String(result.username || 'IG').slice(0, 2).toUpperCase()}</div>
              <div className="comment-main">
                <div><strong>{result.username ? `@${result.username}` : 'Instagram user'}</strong><span>♥ {fmt(result.likes || 0)}</span></div>
                <p>{result.comment}</p>
                <small>{result.topic || 'other'} • {result.emotion || 'neutral'} • {Math.round(Number(result.confidence || 0) * 100)}% confidence</small>
              </div>
              <Pill tone={result.sentiment}>{result.sentiment}</Pill>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
