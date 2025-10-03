#!/bin/bash

# AWS Deployment Script for Inputer Performance Monitor

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
STACK_NAME=${STACK_NAME:-"inputer-performance-monitor"}
ENVIRONMENT=${ENVIRONMENT:-"dev"}
AWS_REGION=${AWS_REGION:-"us-east-1"}

echo -e "${BLUE}🚀 Inputer Performance Monitor - AWS Deployment${NC}"
echo -e "${BLUE}================================================${NC}"

# Check prerequisites
echo -e "${YELLOW}📋 Checking prerequisites...${NC}"

if ! command -v aws &> /dev/null; then
    echo -e "${RED}❌ AWS CLI is not installed${NC}"
    exit 1
fi

if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

# Check AWS credentials
if ! aws sts get-caller-identity &> /dev/null; then
    echo -e "${RED}❌ AWS credentials not configured${NC}"
    echo -e "${YELLOW}   Run: aws configure${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Prerequisites check passed${NC}"

# Get AWS account info
AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
echo -e "${BLUE}📋 Deployment Configuration:${NC}"
echo -e "   AWS Account: ${AWS_ACCOUNT_ID}"
echo -e "   Region: ${AWS_REGION}"
echo -e "   Environment: ${ENVIRONMENT}"
echo -e "   Stack Name: ${STACK_NAME}-${ENVIRONMENT}"

# Prompt for VPC configuration
echo -e "${YELLOW}🏗️  VPC Configuration Required${NC}"
echo -e "Please provide your VPC and subnet information:"

# Get VPC ID
echo -n "VPC ID: "
read VPC_ID

if [[ -z "$VPC_ID" ]]; then
    echo -e "${RED}❌ VPC ID is required${NC}"
    exit 1
fi

# Get subnet IDs
echo -n "Subnet IDs (comma-separated): "
read SUBNET_IDS

if [[ -z "$SUBNET_IDS" ]]; then
    echo -e "${RED}❌ At least one subnet ID is required${NC}"
    exit 1
fi

# Convert comma-separated to array format for CloudFormation
SUBNET_ARRAY=$(echo "$SUBNET_IDS" | sed 's/,/","/g' | sed 's/^/"/' | sed 's/$/"/')

echo -e "${YELLOW}🏗️  Building Docker image...${NC}"

# Create ECR repository if it doesn't exist
REPO_NAME="inputer-performance-monitor"
ECR_URI="${AWS_ACCOUNT_ID}.dkr.ecr.${AWS_REGION}.amazonaws.com/${REPO_NAME}"

if ! aws ecr describe-repositories --repository-names $REPO_NAME --region $AWS_REGION &> /dev/null; then
    echo -e "${YELLOW}📦 Creating ECR repository...${NC}"
    aws ecr create-repository --repository-name $REPO_NAME --region $AWS_REGION
fi

# Get ECR login token
echo -e "${YELLOW}🔐 Logging into ECR...${NC}"
aws ecr get-login-password --region $AWS_REGION | docker login --username AWS --password-stdin $ECR_URI

# Build and tag Docker image
echo -e "${YELLOW}🔨 Building Docker image...${NC}"
docker build -t $REPO_NAME .
docker tag $REPO_NAME:latest $ECR_URI:latest
docker tag $REPO_NAME:latest $ECR_URI:$ENVIRONMENT

# Push image to ECR
echo -e "${YELLOW}📤 Pushing image to ECR...${NC}"
docker push $ECR_URI:latest
docker push $ECR_URI:$ENVIRONMENT

echo -e "${GREEN}✅ Docker image pushed successfully${NC}"

# Deploy CloudFormation stack
echo -e "${YELLOW}☁️  Deploying CloudFormation stack...${NC}"

aws cloudformation deploy \
    --template-file docs/deployment/aws/cloudformation-template.yaml \
    --stack-name "${STACK_NAME}-${ENVIRONMENT}" \
    --parameter-overrides \
        Environment=$ENVIRONMENT \
        VpcId=$VPC_ID \
        SubnetIds=$SUBNET_ARRAY \
    --capabilities CAPABILITY_IAM \
    --region $AWS_REGION

if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ CloudFormation deployment successful${NC}"
else
    echo -e "${RED}❌ CloudFormation deployment failed${NC}"
    exit 1
fi

# Get stack outputs
echo -e "${YELLOW}📋 Getting deployment information...${NC}"

CLUSTER_NAME=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}-${ENVIRONMENT}" \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ClusterName`].OutputValue' \
    --output text)

LOAD_BALANCER_DNS=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}-${ENVIRONMENT}" \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LoadBalancerDNS`].OutputValue' \
    --output text)

RESULTS_BUCKET=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}-${ENVIRONMENT}" \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`ResultsBucket`].OutputValue' \
    --output text)

LAMBDA_ARN=$(aws cloudformation describe-stacks \
    --stack-name "${STACK_NAME}-${ENVIRONMENT}" \
    --region $AWS_REGION \
    --query 'Stacks[0].Outputs[?OutputKey==`LambdaFunctionArn`].OutputValue' \
    --output text)

# Update ECS service to use new image
echo -e "${YELLOW}🔄 Updating ECS service with new image...${NC}"

# Get current task definition
TASK_DEFINITION=$(aws ecs describe-services \
    --cluster $CLUSTER_NAME \
    --services "inputer-${ENVIRONMENT}" \
    --region $AWS_REGION \
    --query 'services[0].taskDefinition' \
    --output text)

# Update task definition with new image
aws ecs describe-task-definition \
    --task-definition $TASK_DEFINITION \
    --region $AWS_REGION \
    --query 'taskDefinition' > /tmp/task-definition.json

# Replace image in task definition
sed -i.bak "s|public.ecr.aws/lambda/python:3.11|$ECR_URI:$ENVIRONMENT|g" /tmp/task-definition.json

# Remove unnecessary fields
jq 'del(.taskDefinitionArn, .revision, .status, .requiresAttributes, .placementConstraints, .compatibilities, .registeredAt, .registeredBy)' /tmp/task-definition.json > /tmp/task-definition-clean.json

# Register new task definition
NEW_TASK_DEF=$(aws ecs register-task-definition \
    --cli-input-json file:///tmp/task-definition-clean.json \
    --region $AWS_REGION \
    --query 'taskDefinition.taskDefinitionArn' \
    --output text)

# Update service
aws ecs update-service \
    --cluster $CLUSTER_NAME \
    --service "inputer-${ENVIRONMENT}" \
    --task-definition $NEW_TASK_DEF \
    --region $AWS_REGION

echo -e "${GREEN}✅ Deployment Complete!${NC}"
echo ""
echo -e "${BLUE}📋 Deployment Information:${NC}"
echo -e "   Cluster: ${CLUSTER_NAME}"
echo -e "   Load Balancer: http://${LOAD_BALANCER_DNS}"
echo -e "   Results Bucket: ${RESULTS_BUCKET}"
echo -e "   Lambda Function: ${LAMBDA_ARN}"
echo ""
echo -e "${BLUE}🎯 Usage Examples:${NC}"
echo ""
echo -e "${YELLOW}Manual analysis via Lambda:${NC}"
echo -e "aws lambda invoke --function-name ${LAMBDA_ARN} \\"
echo -e "  --payload '{\"urls\":[\"https://example.com\"],\"subnets\":[\"${SUBNET_IDS}\"]}' \\"
echo -e "  response.json"
echo ""
echo -e "${YELLOW}Check ECS service status:${NC}"
echo -e "aws ecs describe-services --cluster ${CLUSTER_NAME} --services inputer-${ENVIRONMENT}"
echo ""
echo -e "${YELLOW}View logs:${NC}"
echo -e "aws logs tail /ecs/inputer-${ENVIRONMENT} --follow"
echo ""
echo -e "${YELLOW}Download results:${NC}"
echo -e "aws s3 sync s3://${RESULTS_BUCKET}/ ./results/"
echo ""
echo -e "${GREEN}🎉 Your Inputer Performance Monitor is now running on AWS!${NC}"

# Cleanup temporary files
rm -f /tmp/task-definition.json /tmp/task-definition-clean.json