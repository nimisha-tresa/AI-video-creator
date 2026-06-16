import type { Project } from '@/types/editor'

interface ProjectSidebarProps {
  projects: Project[]
  selectedProjectId: string
  onSelectProject: (projectId: string) => void
}

function statusClass(status: Project['status']): string {
  if (status === 'completed') return 'status status-completed'
  if (status === 'rendering') return 'status status-rendering'
  return 'status status-draft'
}

export function ProjectSidebar({ projects, selectedProjectId, onSelectProject }: ProjectSidebarProps) {
  return (
    <aside className="panel sidebar">
      <div className="panel-header">
        <h2>Projects</h2>
        <button className="ghost-btn" type="button">
          + New
        </button>
      </div>

      <nav className="project-list">
        {projects.map(project => (
          <button
            key={project.id}
            className={`project-item ${project.id === selectedProjectId ? 'active' : ''}`}
            onClick={() => onSelectProject(project.id)}
            type="button"
          >
            <div>
              <p className="project-name">{project.name}</p>
              <p className="project-meta">Updated {project.updatedAt}</p>
            </div>
            <span className={statusClass(project.status)}>{project.status}</span>
          </button>
        ))}
      </nav>
    </aside>
  )
}
