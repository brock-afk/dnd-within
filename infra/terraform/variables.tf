variable "location" {
  description = "Region for every resource, and the only one policy allows."
  type        = string
  default     = "centralus"
}

variable "project" {
  description = "Short project name, used in every resource name."
  type        = string
  default     = "dndwithin"
}

variable "github_repo" {
  description = "GitHub repository (owner/name) whose main branch may log in to Azure."
  type        = string
  default     = "brock-afk/dnd-within"
}
