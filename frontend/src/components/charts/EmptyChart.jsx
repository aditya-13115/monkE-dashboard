export default function EmptyChart({ text = 'No live data has been synced for this view yet.' }) {
  return <div className="chart-empty">{text}</div>
}
