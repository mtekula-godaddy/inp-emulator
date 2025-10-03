# AWS Deployment Guide - Inputer Performance Monitor

## 🚀 Overview

Deploy Inputer Performance Monitor on AWS for scalable, production-ready INP analysis. This guide covers deployment using AWS ECS Fargate, Bedrock for LLM services, and automated infrastructure provisioning.

## 🏗️ Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Application   │    │   Chrome MCP     │    │  AWS Bedrock    │
│  Load Balancer  │────│   ECS Service    │────│  (Claude LLM)   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
         │                        │                       │
         │                        │                       │
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  Lambda Scheduler│    │   S3 Results    │    │   CloudWatch    │
│  (EventBridge)  │    │     Bucket      │    │    Monitoring   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

### Key Components

- **ECS Fargate**: Containerized application deployment
- **AWS Bedrock**: Managed LLM service (Claude models)
- **Application Load Balancer**: Traffic distribution
- **S3**: Results storage and archival
- **Lambda**: Scheduled analysis triggers
- **CloudWatch**: Monitoring, logging, and alerting
- **ECR**: Container image registry

## 📋 Prerequisites

1. **AWS Account** with appropriate permissions
2. **AWS CLI** configured with credentials
3. **Docker** installed locally
4. **VPC** with public subnets (for internet access)
5. **Domain name** (optional, for custom endpoints)

### Required AWS Permissions

Your AWS user/role needs:
- `AmazonECS_FullAccess`
- `AmazonEC2ContainerRegistryFullAccess`
- `CloudFormationFullAccess`
- `IAMFullAccess`
- `AmazonS3FullAccess`
- `AmazonBedrockFullAccess`
- `CloudWatchFullAccess`

## 🚀 Quick Deploy

### 1. Clone and Configure

```bash
git clone <repository-url>
cd inputer

# Make deployment script executable
chmod +x scripts/deploy-aws.sh

# Set environment variables
export ENVIRONMENT=prod
export AWS_REGION=us-east-1
export STACK_NAME=inputer-performance-monitor
```

### 2. Run Deployment Script

```bash
./scripts/deploy-aws.sh
```

The script will prompt for:
- VPC ID
- Subnet IDs (comma-separated)

### 3. Monitor Deployment

```bash
# Check CloudFormation stack status
aws cloudformation describe-stacks --stack-name inputer-performance-monitor-prod

# Monitor ECS service
aws ecs describe-services --cluster inputer-prod --services inputer-prod
```

## 🔧 Manual Deployment Steps

### 1. Create ECR Repository

```bash
# Create repository
aws ecr create-repository --repository-name inputer-performance-monitor

# Get login token
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account-id>.dkr.ecr.us-east-1.amazonaws.com
```

### 2. Build and Push Container

```bash
# Build image
docker build -t inputer-performance-monitor .

# Tag for ECR
docker tag inputer-performance-monitor:latest <account-id>.dkr.ecr.us-east-1.amazonaws.com/inputer-performance-monitor:latest

# Push to ECR
docker push <account-id>.dkr.ecr.us-east-1.amazonaws.com/inputer-performance-monitor:latest
```

### 3. Deploy Infrastructure

```bash
aws cloudformation deploy \
  --template-file docs/deployment/aws/cloudformation-template.yaml \
  --stack-name inputer-performance-monitor-prod \
  --parameter-overrides \
    Environment=prod \
    VpcId=vpc-xxxxxxxx \
    SubnetIds=subnet-xxxxxxxx,subnet-yyyyyyyy \
  --capabilities CAPABILITY_IAM
```

## ⚙️ Configuration

### Environment Variables

The deployment uses these key environment variables:

```bash
# Core application
APP_NAME=inputer-performance-monitor
ENVIRONMENT=prod
AWS_DEFAULT_REGION=us-east-1

# Chrome configuration
CHROME_HEADLESS=true
CHROME_DISABLE_GPU=true
CHROME_NO_SANDBOX=true

# Bedrock LLM
LLM_MODEL=anthropic.claude-3-haiku-20240307-v1:0
LLM_PROVIDER=bedrock

# Storage
RESULTS_BUCKET=inputer-results-prod-123456789012
```

### AWS-Specific Configuration

Edit [`config/aws.yaml`](../config/aws.yaml):

```yaml
llm_agent:
  provider: "bedrock"
  model: "anthropic.claude-3-haiku-20240307-v1:0"  # Cost-effective option
  # model: "anthropic.claude-3-sonnet-20240229-v1:0"  # Higher accuracy

data:
  storage_backend: "s3"
  s3_bucket: "${RESULTS_BUCKET}"

aws:
  bedrock:
    region: "us-east-1"
    models:
      primary: "anthropic.claude-3-haiku-20240307-v1:0"
      fallback: "anthropic.claude-instant-v1"
```

## 🎯 Usage

### Manual Analysis

Trigger analysis via Lambda function:

```bash
aws lambda invoke \
  --function-name inputer-scheduled-prod \
  --payload '{
    "urls": ["https://example.com", "https://app.example.com"],
    "subnets": ["subnet-xxxxxxxx", "subnet-yyyyyyyy"]
  }' \
  response.json
```

### Scheduled Analysis

The deployment includes a weekly scheduled analysis via EventBridge:
- **Schedule**: Every Monday at 9 AM UTC
- **Default URLs**: Configure in CloudFormation template
- **Customization**: Edit the EventBridge rule

### API Access

Access the service via the Application Load Balancer:

```bash
# Get load balancer DNS
LOAD_BALANCER=$(aws cloudformation describe-stacks \
  --stack-name inputer-performance-monitor-prod \
  --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
  --output text)

# Health check
curl http://$LOAD_BALANCER/health

# Trigger analysis (if API endpoints are implemented)
curl -X POST http://$LOAD_BALANCER/analyze \
  -H "Content-Type: application/json" \
  -d '{"urls": ["https://example.com"]}'
```

## 📊 Monitoring and Logging

### CloudWatch Integration

The deployment includes comprehensive monitoring:

1. **ECS Metrics**: CPU, Memory, Network utilization
2. **Custom Metrics**: INP scores, analysis duration, error rates
3. **Log Aggregation**: All application logs in CloudWatch Logs
4. **Dashboard**: Pre-configured CloudWatch dashboard

### View Logs

```bash
# Tail application logs
aws logs tail /ecs/inputer-prod --follow

# Filter for errors
aws logs filter-log-events \
  --log-group-name /ecs/inputer-prod \
  --filter-pattern "ERROR"

# View specific log stream
aws logs get-log-events \
  --log-group-name /ecs/inputer-prod \
  --log-stream-name <stream-name>
```

### Custom Alarms

The deployment creates CloudWatch alarms for:
- High INP scores (> 500ms)
- High error rates (> 10%)
- High memory utilization (> 80%)
- ECS service failures

### Viewing Results

```bash
# List results in S3
aws s3 ls s3://inputer-results-prod-123456789012/results/

# Download results
aws s3 sync s3://inputer-results-prod-123456789012/results/ ./results/

# View latest results
aws s3 cp s3://inputer-results-prod-123456789012/results/latest/ ./latest/ --recursive
```

## 🔍 Troubleshooting

### Common Issues

1. **ECS Tasks Failing to Start**
   ```bash
   # Check task definition
   aws ecs describe-task-definition --task-definition inputer-prod

   # Check stopped tasks
   aws ecs describe-tasks --cluster inputer-prod --tasks <task-arn>
   ```

2. **Bedrock Access Denied**
   ```bash
   # Check Bedrock model access
   aws bedrock list-foundation-models --region us-east-1

   # Test Bedrock permissions
   aws bedrock invoke-model \
     --model-id anthropic.claude-3-haiku-20240307-v1:0 \
     --body '{"anthropic_version": "bedrock-2023-05-31", "max_tokens": 10, "messages": [{"role": "user", "content": "Hello"}]}'
   ```

3. **S3 Access Issues**
   ```bash
   # Test S3 bucket access
   aws s3 ls s3://inputer-results-prod-123456789012/

   # Check bucket policy
   aws s3api get-bucket-policy --bucket inputer-results-prod-123456789012
   ```

4. **Chrome/Chromium Issues**
   ```bash
   # Check ECS task logs for Chrome startup errors
   aws logs filter-log-events \
     --log-group-name /ecs/inputer-prod \
     --filter-pattern "Chrome"
   ```

### Debug Mode

Enable debug logging:

```bash
# Update service with debug environment variable
aws ecs update-service \
  --cluster inputer-prod \
  --service inputer-prod \
  --task-definition inputer-prod \
  --deployment-configuration maximumPercent=200,minimumHealthyPercent=100
```

### Performance Issues

1. **Slow Analysis**: Increase ECS task CPU/memory
2. **High Costs**: Switch to Bedrock Claude Instant or reduce analysis frequency
3. **Network Timeouts**: Check VPC networking and security groups

## 💰 Cost Optimization

### Bedrock Model Selection

| Model | Cost | Speed | Accuracy | Use Case |
|-------|------|-------|----------|----------|
| Claude 3 Haiku | Lowest | Fast | Good | Production, frequent analysis |
| Claude 3 Sonnet | Medium | Medium | High | Complex sites, detailed analysis |
| Claude Instant | Lowest | Fastest | Basic | High-volume, basic analysis |

### ECS Optimization

```yaml
# Use Spot pricing for cost savings
DefaultCapacityProviderStrategy:
  - CapacityProvider: FARGATE_SPOT
    Weight: 80  # 80% spot instances
  - CapacityProvider: FARGATE
    Weight: 20  # 20% on-demand for reliability
```

### Storage Optimization

- Enable S3 lifecycle policies for automatic deletion
- Use S3 Intelligent Tiering for long-term storage
- Compress results before uploading

## 🔐 Security Best Practices

### IAM Permissions

- Use least-privilege IAM roles
- Enable CloudTrail for API auditing
- Rotate access keys regularly

### Network Security

- Deploy in private subnets where possible
- Use Security Groups to restrict access
- Enable VPC Flow Logs

### Data Protection

- Enable S3 bucket encryption
- Use AWS KMS for key management
- Enable CloudWatch Logs encryption

## 📈 Scaling

### Horizontal Scaling

```bash
# Increase ECS service desired count
aws ecs update-service \
  --cluster inputer-prod \
  --service inputer-prod \
  --desired-count 3
```

### Auto Scaling

Add auto scaling to the CloudFormation template:

```yaml
AutoScalingTarget:
  Type: AWS::ApplicationAutoScaling::ScalableTarget
  Properties:
    ServiceNamespace: ecs
    ResourceId: !Sub 'service/${InputerCluster}/${Service}'
    ScalableDimension: ecs:service:DesiredCount
    MinCapacity: 1
    MaxCapacity: 10
    RoleARN: !Sub 'arn:aws:iam::${AWS::AccountId}:role/aws-service-role/ecs.application-autoscaling.amazonaws.com/AWSServiceRoleForApplicationAutoScaling_ECSService'
```

## 🔄 CI/CD Integration

### GitHub Actions Example

```yaml
# .github/workflows/deploy-aws.yml
name: Deploy to AWS
on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2

      - name: Configure AWS credentials
        uses: aws-actions/configure-aws-credentials@v1
        with:
          aws-access-key-id: ${{ secrets.AWS_ACCESS_KEY_ID }}
          aws-secret-access-key: ${{ secrets.AWS_SECRET_ACCESS_KEY }}
          aws-region: us-east-1

      - name: Deploy to AWS
        run: ./scripts/deploy-aws.sh
```

## 📋 Maintenance

### Regular Tasks

1. **Update Container Images**: Rebuild and deploy monthly
2. **Review Costs**: Monitor Bedrock and ECS costs
3. **Update Dependencies**: Keep Python packages current
4. **Backup Configuration**: Export CloudFormation templates

### Monitoring Health

```bash
# Check service health
aws ecs describe-services --cluster inputer-prod --services inputer-prod

# Check recent errors
aws logs filter-log-events \
  --log-group-name /ecs/inputer-prod \
  --start-time $(date -d '1 hour ago' +%s)000 \
  --filter-pattern "ERROR"
```

## 🆘 Support

- **AWS Documentation**: [ECS User Guide](https://docs.aws.amazon.com/AmazonECS/latest/userguide/)
- **Bedrock Documentation**: [Amazon Bedrock User Guide](https://docs.aws.amazon.com/bedrock/latest/userguide/)
- **CloudFormation**: [Template Reference](https://docs.aws.amazon.com/AWSCloudFormation/latest/UserGuide/)

For project-specific issues, refer to the main [README.md](../README.md) troubleshooting section.