export default function BrandFooter({ className = '', children }) {
  const year = new Date().getFullYear()

  return <footer className={`brand-footer ${className}`.trim()}>
    <span>© {year} Auron FIN CRM. All rights reserved.</span>
    <span className="brand-footer-powered">Powered by <a href="https://alphaauron.com/" target="_blank" rel="noopener noreferrer">Alpha Auron</a></span>
    {children}
  </footer>
}
