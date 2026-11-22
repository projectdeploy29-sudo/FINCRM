import { useState, useMemo } from 'react'
import './OrganizationHierarchyView.css'

function initials(name) {
  if (!name) return '?'
  const parts = name.trim().split(/\s+/)
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
}

export default function OrganizationHierarchyView({ data }) {
  const [collapsedDepts, setCollapsedDepts] = useState({})
  const [search, setSearch] = useState('')

  const org = data?.organization || {}
  const departments = data?.departments || []
  const unassignedTeams = data?.unassigned_teams || []
  const unassignedEmployees = data?.unassigned_employees || []

  const stats = useMemo(() => [
    { label: 'Departments', value: data?.total_departments ?? departments.length },
    { label: 'Teams', value: data?.total_teams ?? departments.reduce((acc, d) => acc + (d.teams?.length || 0), 0) + unassignedTeams.length },
    { label: 'Managers', value: data?.total_managers ?? departments.filter((d) => d.manager).length },
    { label: 'Team Leads', value: data?.total_team_leads ?? departments.reduce((acc, d) => acc + (d.teams?.filter((t) => t.team_lead)?.length || 0), 0) },
    { label: 'Employees', value: data?.total_employees ?? departments.reduce((acc, d) => acc + (d.teams?.reduce((tAcc, t) => tAcc + (t.employees?.length || 0), 0) + (d.unassigned_team_employees?.length || 0)), 0) + unassignedEmployees.length },
  ], [data, departments, unassignedTeams, unassignedEmployees])

  function toggleDept(deptId) {
    setCollapsedDepts((current) => ({
      ...current,
      [deptId]: !current[deptId],
    }))
  }

  function toggleAll() {
    const allCollapsed = departments.every((d) => collapsedDepts[d.id])
    const next = {}
    departments.forEach((d) => { next[d.id] = !allCollapsed })
    setCollapsedDepts(next)
  }

  const query = search.trim().toLowerCase()

  const filteredDepartments = useMemo(() => {
    if (!query) return departments
    return departments.map((dept) => {
      const matchDept = dept.name.toLowerCase().includes(query) || (dept.description && dept.description.toLowerCase().includes(query))
      const matchManager = dept.manager && (
        dept.manager.name.toLowerCase().includes(query) ||
        (dept.manager.code && dept.manager.code.toLowerCase().includes(query)) ||
        (dept.manager.designation && dept.manager.designation.toLowerCase().includes(query)) ||
        (dept.manager.email && dept.manager.email.toLowerCase().includes(query))
      )
      const matchingTeams = (dept.teams || []).map((team) => {
        const matchTeam = team.name.toLowerCase().includes(query)
        const matchLead = team.team_lead && (
          team.team_lead.name.toLowerCase().includes(query) ||
          (team.team_lead.code && team.team_lead.code.toLowerCase().includes(query)) ||
          (team.team_lead.email && team.team_lead.email.toLowerCase().includes(query))
        )
        const matchingEmployees = (team.employees || []).filter((emp) => (
          emp.name.toLowerCase().includes(query) ||
          (emp.code && emp.code.toLowerCase().includes(query)) ||
          (emp.designation && emp.designation.toLowerCase().includes(query)) ||
          (emp.email && emp.email.toLowerCase().includes(query))
        ))
        if (matchTeam || matchLead || matchingEmployees.length > 0) {
          return { ...team, employees: matchTeam || matchLead ? team.employees : matchingEmployees }
        }
        return null
      }).filter(Boolean)

      const matchingDirect = (dept.unassigned_team_employees || []).filter((emp) => (
        emp.name.toLowerCase().includes(query) ||
        (emp.code && emp.code.toLowerCase().includes(query)) ||
        (emp.designation && emp.designation.toLowerCase().includes(query))
      ))

      if (matchDept || matchManager || matchingTeams.length > 0 || matchingDirect.length > 0) {
        return {
          ...dept,
          teams: matchDept || matchManager ? dept.teams : matchingTeams,
          unassigned_team_employees: matchDept || matchManager ? dept.unassigned_team_employees : matchingDirect,
        }
      }
      return null
    }).filter(Boolean)
  }, [departments, query])

  if (!data) return <p className="hierarchy-empty-note">No hierarchy information available.</p>

  return (
    <div className="hierarchy-container">
      {/* Summary Metrics */}
      <div className="hierarchy-summary-bar">
        {stats.map((stat) => (
          <div key={stat.label} className="hierarchy-stat-card">
            <span className="stat-label">{stat.label}</span>
            <span className="stat-value">{stat.value}</span>
          </div>
        ))}
      </div>

      {/* Search & Collapse Controls */}
      <div className="hierarchy-controls">
        <div className="hierarchy-search-box">
          <input
            type="search"
            placeholder="Search departments, managers, team leads, or employees…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <button type="button" className="hierarchy-toggle-btn" onClick={toggleAll}>
          {departments.every((d) => collapsedDepts[d.id]) ? 'Expand all departments' : 'Collapse all departments'}
        </button>
      </div>

      {/* Departments Tree */}
      <div className="hierarchy-tree">
        {filteredDepartments.length === 0 ? (
          <p className="hierarchy-empty-note">
            {departments.length === 0 ? 'No departments defined in this organization yet.' : 'No matching departments or staff found.'}
          </p>
        ) : (
          filteredDepartments.map((dept) => {
            const isCollapsed = collapsedDepts[dept.id]
            const manager = dept.manager
            const teams = dept.teams || []
            const directStaff = dept.unassigned_team_employees || []

            return (
              <section key={dept.id} className="hierarchy-dept-card">
                <header className="hierarchy-dept-header" onClick={() => toggleDept(dept.id)}>
                  <div className="hierarchy-dept-title">
                    <span>{isCollapsed ? '▶' : '▼'}</span>
                    <div>
                      <h3>{dept.name}</h3>
                      {dept.description && <p className="hierarchy-dept-desc">{dept.description}</p>}
                    </div>
                  </div>
                  <span className={`hierarchy-badge ${dept.is_active ? 'active' : 'inactive'}`}>
                    {dept.is_active ? 'Active' : 'Inactive'}
                  </span>
                </header>

                {!isCollapsed && (
                  <div className="hierarchy-dept-body">
                    {/* Department Manager */}
                    <div className="hierarchy-manager-section">
                      <span className="hierarchy-section-title">Department Manager</span>
                      {manager ? (
                        <div className="hierarchy-person-card hierarchy-manager-card">
                          <div className="hierarchy-person-info">
                            <div className="hierarchy-avatar">{initials(manager.name)}</div>
                            <div className="hierarchy-person-details">
                              <h4>
                                {manager.name}
                                {manager.code && <span className="hierarchy-person-code">{manager.code}</span>}
                              </h4>
                              <p className="hierarchy-person-role">{manager.designation || 'Department Manager'}</p>
                            </div>
                          </div>
                          <div className="hierarchy-person-contact">
                            {manager.email && <a href={`mailto:${manager.email}`}>{manager.email}</a>}
                            {manager.phone && <a href={`tel:${manager.phone}`}>{manager.phone}</a>}
                          </div>
                        </div>
                      ) : (
                        <p className="hierarchy-empty-note">No manager assigned to this department.</p>
                      )}
                    </div>

                    {/* Teams under Department */}
                    <div className="hierarchy-manager-section">
                      <span className="hierarchy-section-title">Teams ({teams.length})</span>
                      {teams.length === 0 ? (
                        <p className="hierarchy-empty-note">No teams in this department.</p>
                      ) : (
                        <div className="hierarchy-teams-container">
                          {teams.map((team) => {
                            const teamLead = team.team_lead
                            const employees = team.employees || []

                            return (
                              <article key={team.id} className="hierarchy-team-card">
                                <header className="hierarchy-team-header">
                                  <h4>{team.name}</h4>
                                  <span className={`hierarchy-badge ${team.is_active ? 'active' : 'inactive'}`}>
                                    {team.is_active ? 'Active' : 'Inactive'}
                                  </span>
                                </header>
                                {team.description && <p className="hierarchy-dept-desc">{team.description}</p>}

                                {/* Team Lead */}
                                <div className="hierarchy-team-lead-section">
                                  <span className="hierarchy-section-title">Team Lead</span>
                                  {teamLead ? (
                                    <div className="hierarchy-person-card">
                                      <div className="hierarchy-person-info">
                                        <div className="hierarchy-avatar tl-avatar">{initials(teamLead.name)}</div>
                                        <div className="hierarchy-person-details">
                                          <h4>
                                            {teamLead.name}
                                            {teamLead.code && <span className="hierarchy-person-code">{teamLead.code}</span>}
                                          </h4>
                                          <p className="hierarchy-person-role">Team Lead</p>
                                        </div>
                                      </div>
                                      <div className="hierarchy-person-contact">
                                        {teamLead.email && <a href={`mailto:${teamLead.email}`}>{teamLead.email}</a>}
                                        {teamLead.phone && <a href={`tel:${teamLead.phone}`}>{teamLead.phone}</a>}
                                      </div>
                                    </div>
                                  ) : (
                                    <p className="hierarchy-empty-note">No team lead assigned.</p>
                                  )}
                                </div>

                                {/* Team Members */}
                                <div className="hierarchy-team-members-section">
                                  <span className="hierarchy-section-title">Members ({employees.length})</span>
                                  {employees.length === 0 ? (
                                    <p className="hierarchy-empty-note">No employees in this team.</p>
                                  ) : (
                                    <div className="hierarchy-employees-grid">
                                      {employees.map((emp) => (
                                        <div key={emp.id} className="hierarchy-employee-pill">
                                          <div className="emp-top">
                                            <span className="emp-name">{emp.name}</span>
                                            {emp.employment_status && (
                                              <span className={`hierarchy-badge ${emp.employment_status === 'active' ? 'active' : 'inactive'}`}>
                                                {emp.employment_status.replace('_', ' ')}
                                              </span>
                                            )}
                                          </div>
                                          <span className="emp-designation">{emp.designation || emp.role?.name || 'Employee'}</span>
                                          <div className="emp-meta">
                                            <span>{emp.code || '—'}</span>
                                            {emp.email && <a href={`mailto:${emp.email}`}>{emp.email}</a>}
                                          </div>
                                        </div>
                                      ))}
                                    </div>
                                  )}
                                </div>
                              </article>
                            )
                          })}
                        </div>
                      )}
                    </div>

                    {/* Direct Department Staff (if any) */}
                    {directStaff.length > 0 && (
                      <div className="hierarchy-manager-section">
                        <span className="hierarchy-section-title">Direct Department Staff ({directStaff.length})</span>
                        <div className="hierarchy-employees-grid">
                          {directStaff.map((emp) => (
                            <div key={emp.id} className="hierarchy-employee-pill">
                              <div className="emp-top">
                                <span className="emp-name">{emp.name}</span>
                                {emp.employment_status && (
                                  <span className={`hierarchy-badge ${emp.employment_status === 'active' ? 'active' : 'inactive'}`}>
                                    {emp.employment_status.replace('_', ' ')}
                                  </span>
                                )}
                              </div>
                              <span className="emp-designation">{emp.designation || emp.role?.name || 'Employee'}</span>
                              <div className="emp-meta">
                                <span>{emp.code || '—'}</span>
                                {emp.email && <a href={`mailto:${emp.email}`}>{emp.email}</a>}
                              </div>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </section>
            )
          })
        )}

        {/* Unassigned Teams (outside of departments) */}
        {unassignedTeams.length > 0 && (
          <section className="hierarchy-dept-card">
            <header className="hierarchy-dept-header">
              <div className="hierarchy-dept-title">
                <h3>Unassigned Teams ({unassignedTeams.length})</h3>
                <p className="hierarchy-dept-desc">Teams not currently mapped to a department</p>
              </div>
            </header>
            <div className="hierarchy-dept-body">
              <div className="hierarchy-teams-container" style={{ borderLeft: 'none', paddingLeft: 0 }}>
                {unassignedTeams.map((team) => (
                  <article key={team.id} className="hierarchy-team-card">
                    <header className="hierarchy-team-header">
                      <h4>{team.name}</h4>
                    </header>
                    <div className="hierarchy-employees-grid">
                      {(team.employees || []).map((emp) => (
                        <div key={emp.id} className="hierarchy-employee-pill">
                          <span className="emp-name">{emp.name}</span>
                          <span className="emp-designation">{emp.designation || 'Employee'}</span>
                        </div>
                      ))}
                    </div>
                  </article>
                ))}
              </div>
            </div>
          </section>
        )}

        {/* Unassigned Staff */}
        {unassignedEmployees.length > 0 && (
          <section className="hierarchy-dept-card">
            <header className="hierarchy-dept-header">
              <div className="hierarchy-dept-title">
                <h3>Unassigned Employees ({unassignedEmployees.length})</h3>
                <p className="hierarchy-dept-desc">Staff without a department or team assignment</p>
              </div>
            </header>
            <div className="hierarchy-dept-body">
              <div className="hierarchy-employees-grid">
                {unassignedEmployees.map((emp) => (
                  <div key={emp.id} className="hierarchy-employee-pill">
                    <span className="emp-name">{emp.name}</span>
                    <span className="emp-designation">{emp.designation || 'Employee'}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>
        )}
      </div>
    </div>
  )
}
