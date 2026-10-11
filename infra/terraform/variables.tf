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
  description = "GitHub repository whose main branch may log in to Azure, as it appears in the OIDC subject (owner@id/name@id)."
  type        = string
  default     = "brock-afk@53913816/dnd-within@1413773531"
}
