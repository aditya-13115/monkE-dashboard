import { BarChart3, Bot, MessageCircle, RefreshCw, Smile, Users } from 'lucide-react'
import { Cell, Bar, BarChart, CartesianGrid, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Metric, Pill, SectionHeader } from '../../components/common/UI'
import { useCampaignSentiment } from '../../hooks/useCampaignJobs'
import { fmt } from '../../lib/metrics'

const tones = ['#10b981', '#94a3b8', '#f43f5e']

function AnalysisBody({ result, readonly = false, onRun }) {
  const summary = result?.summary || {}
  const collection = result?.collection || {}
  const topics = Array.isArray(result?.topics) ? result.topics : []
  const emotions = Array.isArray(result?.emotions) ? result.emotions : []
  const postBreakdown = Array.isArray(result?.postBreakdown) ? result.postBreakdown.slice(0, 12) : []
  const pie = [
    { name: 'Positive', value: Number(summary.positive || 0) },
    { name: 'Neutral', value: Number(summary.neutral || 0) },
    { name: 'Negative', value: Number(summary.negative || 0) },
  ]

  return (
    <div className="campaign-sentiment-body">
      <div className="metric-grid sentiment-inline-metrics">
        <Metric icon={MessageCircle} label="Sampled comments" value={fmt(collection.sampledComments || result?.sample?.selected || 0)} sub="Randomly sampled across posts + reels" accent="violet" />
        <Metric icon={Smile} label="Positive" value={`${Number(summary.positivePct || 0).toFixed(1)}%`} sub={`${summary.positive || 0} comments`} accent="mint" />
        <Metric icon={Bot} label="Neutral" value={`${Number(summary.neutralPct || 0).toFixed(1)}%`} sub={`${summary.neutral || 0} comments`} accent="blue" />
        <Metric icon={BarChart3} label="Negative" value={`${Number(summary.negativePct || 0).toFixed(1)}%`} sub={`${summary.negative || 0} comments`} accent="pink" />
        <Metric icon={Users} label="Coverage" value={`${collection.postsWithComments || 0}/${collection.attemptedPosts || 0}`} sub={`${collection.reelsWithComments || 0}/${collection.reels || 0} reels with comments`} accent="orange" />
      </div>

      <div className="grid-two campaign-sentiment-grid">
        <div className="panel nested-panel">
          <SectionHeader eyebrow="Campaign tone" title="Overall audience sentiment" />
          <div className="chart"><ResponsiveContainer width="100%" height={245}>
            <PieChart>
              <Pie data={pie} dataKey="value" nameKey="name" innerRadius={56} outerRadius={86} paddingAngle={3}>
                {pie.map((_, index) => <Cell key={index} fill={tones[index]} />)}
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
          <SectionHeader eyebrow="Conversation themes" title="Top campaign topics" />
          {topics.length ? <div className="topic-list">
            {topics.slice(0, 8).map(item => {
              const max = Math.max(1, ...topics.map(topic => Number(topic.count || 0)))
              return <div className="topic-row" key={item.topic}><span>{item.topic}</span><div className="topic-track"><b style={{ width: `${Math.min(100, Number(item.count || 0) / max * 100)}%` }} /></div><strong>{item.count}</strong></div>
            })}
          </div> : <div className="muted">No topics were returned.</div>}
          {emotions.length ? <div className="sentiment-emotion-list">{emotions.slice(0, 6).map(item => <Pill key={item.emotion}>{item.emotion} · {item.count}</Pill>)}</div> : null}
        </div>
      </div>

      {postBreakdown.length ? <div className="panel nested-panel">
        <SectionHeader eyebrow="Placement comparison" title="Sentiment across the campaign" copy="The same campaign-level comment sample is grouped back to the posts and reels that contributed it." />
        <div className="chart"><ResponsiveContainer width="100%" height={310}>
          <BarChart data={postBreakdown} margin={{ top: 8, right: 12, bottom: 35, left: 0 }}>
            <CartesianGrid strokeDasharray="4 4" vertical={false} />
            <XAxis dataKey="username" tickLine={false} axisLine={false} angle={-28} textAnchor="end" height={60} />
            <YAxis allowDecimals={false} tickLine={false} axisLine={false} />
            <Tooltip />
            <Bar dataKey="positive" stackId="tone" fill="#10b981" name="Positive" />
            <Bar dataKey="neutral" stackId="tone" fill="#94a3b8" name="Neutral" />
            <Bar dataKey="negative" stackId="tone" fill="#f43f5e" name="Negative" />
          </BarChart>
        </ResponsiveContainer></div>
      </div> : null}

      {!readonly && result?.partial ? <div className="analysis-note">Some comment-analysis batches failed. Existing results are shown and can be re-run.</div> : null}
    </div>
  )
}

export default function CampaignSentimentPanel({ campaignId, initialResult, readonly = false }) {
  const { result, job, error, start, running } = useCampaignSentiment(campaignId, initialResult, !readonly)

  async function run() {
    try { await start(Boolean(result)) } catch {}
  }

  return (
    <div className="panel campaign-sentiment-panel">
      <div className="campaign-sentiment-head">
        <div>
          <div className="eyebrow">AI audience voice • whole campaign</div>
          <h2>{result ? 'Campaign-wide sentiment' : 'Campaign sentiment analysis'}</h2>
          <p>{result ? `A single audience sample across the campaign, including reels and posts. ${result.collection?.sampledComments || result.sample?.selected || 0} comments analyzed.` : 'No post-by-post clicking required. Monk-E collects a small random sample from every post/reel, then analyzes the campaign audience as one dataset.'}</p>
        </div>
        {!readonly && <button className="primary-btn" onClick={run} disabled={running}>
          <RefreshCw size={14} className={running ? 'spin' : ''} />
          {running ? `${job?.phase === 'ai' ? 'Analyzing campaign…' : `Collecting ${job?.processed || 0}/${job?.total || 0}…`}` : result ? 'Re-analyze campaign' : 'Analyze whole campaign'}
        </button>}
        {readonly && <Pill>READ ONLY</Pill>}
      </div>

      {running && <div className="campaign-job-status">
        <div className="campaign-job-progress"><span style={{ width: `${Number(job?.percent || 0)}%` }} /></div>
        <div><strong>{job?.message || 'Working…'}</strong><span>{Number(job?.percent || 0).toFixed(0)}%</span></div>
      </div>}

      {error && <div className="error-banner">{error}</div>}
      {result ? <AnalysisBody result={result} readonly={readonly} onRun={run} /> : !running && <div className="campaign-sentiment-empty"><Bot size={20} /><span>Run campaign analysis once. The result is cached and is also available in read-only POC links.</span></div>}
    </div>
  )
}
