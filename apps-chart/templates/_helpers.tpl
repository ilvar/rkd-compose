{{/*
Expand the name of the chart.
*/}}
{{- define "apps-chart.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "apps-chart.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Parse user ID from user:group format
*/}}
{{- define "apps-chart.userID" -}}
{{- if . }}
{{- $userStr := toString . }}
{{- $parts := splitList ":" $userStr }}
{{- if gt (len $parts) 0 }}
{{- toString (index $parts 0) }}
{{- else }}
1000
{{- end }}
{{- else }}
1000
{{- end }}
{{- end }}

{{/*
Parse group ID from user:group format
*/}}
{{- define "apps-chart.groupID" -}}
{{- if . }}
{{- $userStr := toString . }}
{{- $parts := splitList ":" $userStr }}
{{- if gt (len $parts) 1 }}
{{- toString (index $parts 1) }}
{{- else }}
1000
{{- end }}
{{- else }}
1000
{{- end }}
{{- end }}

{{/*
Get rkd.pw hosts from a list
*/}}
{{- define "apps-chart.getRkdPwHosts" -}}
{{- $rkdHosts := list }}
{{- range . }}
{{- if contains ".rkd.pw" . }}
{{- $rkdHosts = append $rkdHosts . }}
{{- end }}
{{- end }}
{{- if gt (len $rkdHosts) 0 }}
{{- $rkdHosts | toJson }}
{{- else }}
[]
{{- end }}
{{- end }}

