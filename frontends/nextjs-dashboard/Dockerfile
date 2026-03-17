FROM node:20-alpine

WORKDIR /app

COPY frontends/nextjs-dashboard/package*.json ./

RUN npm install

COPY frontends/nextjs-dashboard/ .

RUN npm run build

EXPOSE 3000

CMD ["npm", "start"]
