pipeline {
    agent {
        label 'docker-runner' // Run build stages inside dynamic Docker or K8s agents
    }
    
    options {
        timeout(time: 1, unit: 'HOURS')
        buildDiscarder(logRotator(numToKeepStr: '30'))
        ansiColor('xterm')
    }
    
    environment {
        REGISTRY = "AWS_ACCOUNT_ID.dkr.ecr.us-east-1.amazonaws.com"
        REGISTRY_CREDENTIALS_ID = "aws-ecr-credentials"
        CHANGED_SERVICES = ""
    }
    
    stages {
        stage('Detect Changes') {
            steps {
                script {
                    // Define all microservices in the monorepo
                    def services = ["api-gateway", "auth-service", "audit-service", "qa-service", "history-service", "criteria-service", "ingestion-service", "scraper-worker"]
                    def changed = []
                    
                    // Compare against the target branch (e.g. origin/main) or the previous commit
                    def targetBranch = env.CHANGE_TARGET ?: "origin/main"
                    
                    for (service in services) {
                        def hasChanges = sh(
                            script: "git diff --name-only ${targetBranch}...HEAD | grep '^services/${service}/' || true",
                            returnStdout: true
                        ).trim()
                        
                        if (hasChanges) {
                            changed.add(service)
                        }
                    }
                    
                    // If shared packages/wcag-common changes, we rebuild and retest all services
                    def commonChanges = sh(
                        script: "git diff --name-only ${targetBranch}...HEAD | grep '^packages/wcag-common/' || true",
                        returnStdout: true
                    ).trim()
                    
                    if (commonChanges) {
                        changed = services
                        echo "wcag-common changed; marking all microservices for build and verification."
                    }
                    
                    env.CHANGED_SERVICES = changed.join(",")
                    echo "Services selected for build/test: ${env.CHANGED_SERVICES}"
                }
            }
        }
        
        stage('Parallel Verification') {
            when {
                expression { env.CHANGED_SERVICES != "" }
            }
            steps {
                script {
                    def tasks = [:]
                    def activeServices = env.CHANGED_SERVICES.split(",")
                    
                    for (serviceName in activeServices) {
                        def service = serviceName // Capture loop variable context
                        tasks[service] = {
                            node('docker-runner') {
                                stage("Verify ${service}") {
                                    echo "Installing dependencies and running tests for ${service}..."
                                    // Use uv to run service tests in clean environment
                                    sh "uv run --project services/${service} pytest"
                                }
                            }
                        }
                    }
                    parallel tasks
                }
            }
        }
        
        stage('Docker Compilation & Push') {
            when {
                expression { env.CHANGED_SERVICES != "" }
            }
            steps {
                script {
                    def activeServices = env.CHANGED_SERVICES.split(",")
                    
                    // Authenticate and push to Amazon ECR
                    docker.withRegistry("https://${env.REGISTRY}", "ecr:${env.REGISTRY_CREDENTIALS_ID}") {
                        for (serviceName in activeServices) {
                            def service = serviceName
                            stage("Build & Push ${service}") {
                                def tag = "${env.BUILD_NUMBER}"
                                def image = docker.build("${env.REGISTRY}/wcag-${service}:${tag}", "-f services/${service}/Dockerfile .")
                                image.push()
                                image.push("latest")
                            }
                        }
                    }
                }
            }
        }
    }
}
