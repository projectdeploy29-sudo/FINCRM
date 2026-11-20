import { useEffect, useState } from 'react'
import { unwrapList } from '../api'
import RecordForm from './RecordForm'

export default function TodayPage({ api }) {
  const [tasks, setTasks] = useState([])
  const [followups, setFollowups] = useState([])
  const [completingFollowup, setCompletingFollowup] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  async function load() {
    setBusy(true); setError('')
    try {
      const [taskRows, followupRows] = await Promise.all([api.get('/tasks/my-tasks/'), api.get('/followups/today/')])
      const now=new Date(); const today=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0, 10)
      setTasks(unwrapList(taskRows).filter((task) => task.status !== 'COMPLETED' && task.status !== 'CANCELLED' && String(task.due_date || '').slice(0, 10) <= today))
      setFollowups(unwrapList(followupRows))
    } catch (exception) { setError(exception.message) } finally { setBusy(false) }
  }
  useEffect(() => { load() }, [])
  async function completeFollowup(row, payload) {
    const collection=row.kind==='customer'?'customers':row.kind==='lead'?'leads':'applications'
    await api.patch(`/followups/${collection}/${row.id}/`,{...payload,status:'COMPLETED'})
    setCompletingFollowup(null)
    await load()
  }
  async function transitionTask(row,status) {
    try { await api.post(`/tasks/${row.id}/transition/`,{status}); await load() } catch (exception) { setError(exception.message) }
  }
  return <section>
    <h2>Tasks and follow-ups</h2>
    <button type="button" onClick={load} disabled={busy}>Refresh today</button>
    {error && <p role="alert">{error}</p>}
    <h3>Today’s follow-ups</h3>
    {followups.length ? <table><thead><tr><th>Type</th><th>Record</th><th>Scheduled</th><th>Notes</th><th>Action</th></tr></thead><tbody>{followups.map((row) => <tr key={`${row.kind}-${row.id}`}><td>{row.followup_type}</td><td>{row.contact_name || row.contact_record_code || row.kind}</td><td>{new Date(row.scheduled_at).toLocaleString()}</td><td>{row.notes}</td><td><button type="button" onClick={() => setCompletingFollowup(row)}>Mark complete</button></td></tr>)}</tbody></table> : <p>No follow-ups due today.</p>}
    {completingFollowup && <RecordForm key={`complete-followup-${completingFollowup.id}`} fields={[{ name: 'outcome', label: 'Outcome', type: 'textarea', required: true }]} initial={{}} api={api} title="Complete follow-up" submitLabel="Mark complete" onCancel={() => setCompletingFollowup(null)} onSubmit={(payload) => completeFollowup(completingFollowup, payload)} />}
    <h3>Tasks due today or overdue</h3>
    {tasks.length ? <table><thead><tr><th>Task</th><th>Status</th><th>Due</th><th>Priority</th><th>Action</th></tr></thead><tbody>{tasks.map((row) => <tr key={row.id}><td>{row.title}</td><td>{row.status}</td><td>{row.due_date}</td><td>{row.priority}</td><td>{row.status==='PENDING' ? <button type="button" onClick={() => transitionTask(row,'IN_PROGRESS')}>Start task</button> : row.status==='IN_PROGRESS' ? <button type="button" onClick={() => transitionTask(row,'COMPLETED')}>Complete task</button> : null}</td></tr>)}</tbody></table> : <p>No tasks due today.</p>}
  </section>
}
