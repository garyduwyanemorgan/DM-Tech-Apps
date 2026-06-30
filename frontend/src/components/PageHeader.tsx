import React from 'react'

interface PageHeaderProps {
  title: string
  subtitle?: string
  icon?: string
}

export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, icon }) => (
  <div className="page-header">
    <h1>{icon ? `${icon} ${title}` : title}</h1>
    {subtitle && <p>{subtitle}</p>}
  </div>
)
