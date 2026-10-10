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
